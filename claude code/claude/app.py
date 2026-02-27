from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psutil
import time
import threading
import json
from datetime import datetime, timedelta
from collections import defaultdict
import os

app = Flask(__name__)
CORS(app)

# Global data storage
activity_data = defaultdict(lambda: {
    'total_time': 0,
    'cpu_usage': 0,
    'category': 'unknown',
    'last_update': None,
    'source': None
})

config = {
    'emission_factor': 0.475,  # kg CO2 per kWh
    'tracking_enabled': True,
    'idle_threshold': 300  # 5 minutes
}

# Process tracking
tracked_processes = {}
last_activity_time = time.time()
is_idle = False

# System processes to EXCLUDE (comprehensive list)
SYSTEM_PROCESSES_BLACKLIST = {
    # Windows System Processes
    'system', 'system idle process', 'smss.exe', 'csrss.exe', 'wininit.exe',
    'winlogon.exe', 'services.exe', 'lsass.exe', 'lsaiso.exe', 'svchost.exe',
    'taskhost.exe', 'taskhostw.exe', 'dwm.exe', 'explorer.exe', 'sihost.exe',
    'runtimebroker.exe', 'searchindexer.exe', 'searchprotocolhost.exe',
    'searchfilterhost.exe', 'conhost.exe', 'fontdrvhost.exe', 'wudfhost.exe',
    'dashost.exe', 'memory compression', 'registry', 'secure system',
    'ntoskrnl.exe', 'spoolsv.exe', 'audiodg.exe', 'ctfmon.exe',
    'wlanext.exe', 'msmpeng.exe', 'nissrv.exe', 'securityhealthservice.exe',
    'sgrmbroker.exe', 'startmenuexperiencehost.exe', 'shellexperiencehost.exe',
    'textinputhost.exe', 'lockapp.exe', 'applicationframehost.exe',
    'windowsinternal.composableshell.experiences.textinput.inputapp.exe',
    'systemsettings.exe', 'settingssynchost.exe', 'useroobebroker.exe',
    
    # Windows Defender & Security
    'msmpeng.exe', 'nissrv.exe', 'securityhealthsystray.exe',
    'securityhealthservice.exe', 'windefend.exe', 'mpcmdrun.exe',
    
    # Windows Update & Management
    'wuauclt.exe', 'trustedinstaller.exe', 'tiworker.exe', 'usoclient.exe',
    'musnotification.exe', 'musnotificationux.exe',
    
    # Network & Connection
    'dashost.exe', 'netsh.exe', 'ping.exe', 'ipconfig.exe',
    
    # Driver & Hardware
    'nvdisplay.container.exe', 'nvcontainer.exe', 'nvprofileupdater.exe',
    'atieclxx.exe', 'atiesrxx.exe', 'igfxem.exe', 'igfxpers.exe',
    'igfxtray.exe', 'hkcmd.exe', 'igfxsrvc.exe',
    
    # MacOS System Processes
    'kernel_task', 'launchd', 'loginwindow', 'windowserver', 'dock',
    'finder', 'systemuiserver', 'coreaudiod', 'corespotlightd', 'mds',
    'mds_stores', 'mdworker', 'trustd', 'securityd', 'parentalcontrolsd',
    'softwareupdated', 'notifyd', 'distnoted', 'cfprefsd', 'useractivityd',
    'bird', 'cloudd', 'apsd', 'rapportd', 'airplayuiagent',
    
    # Linux System Processes
    'systemd', 'init', 'kthreadd', 'ksoftirqd', 'kworker', 'kswapd',
    'migration', 'watchdog', 'cpuhp', 'kdevtmpfs', 'netns', 'khungtaskd',
    'oom_reaper', 'writeback', 'kcompactd', 'kblockd', 'kintegrityd',
    'kworker', 'irq', 'acpi', 'thermal', 'scsi', 'ata_sff', 'md',
    'devfreq_wq', 'watchdogd', 'kauditd', 'khugepaged', 'crypto',
    
    # Generic System/Background
    'idle', 'system32', 'syswow64', 'backgroundtaskhost.exe',
    'taskmgr.exe', 'perfmon.exe', 'resmon.exe', 'mmc.exe',
}

# Additional filtering patterns
SYSTEM_PROCESS_PATTERNS = [
    'windows', 'microsoft', 'update', 'defender', 'system',
    'svc', 'host', 'service', 'driver', 'helper', 'agent',
    'daemon', 'background', 'runtime', 'broker', 'protocol'
]

def is_system_process(process_name):
    """
    Determine if a process is a system process (should be excluded)
    Returns True if it's a system process, False if it's a user application
    """
    if not process_name:
        return True
    
    process_lower = process_name.lower()
    
    # Check exact match in blacklist
    if process_lower in SYSTEM_PROCESSES_BLACKLIST:
        return True
    
    # Remove common file extensions
    base_name = process_lower.replace('.exe', '').replace('.app', '').replace('.bin', '')
    
    # Check if base name is in blacklist
    if base_name in SYSTEM_PROCESSES_BLACKLIST:
        return True
    
    # Check for system patterns (but be more selective)
    pattern_matches = sum(1 for pattern in SYSTEM_PROCESS_PATTERNS if pattern in base_name)
    if pattern_matches >= 2:
        return True
    
    # Specifically exclude if it's clearly a Windows system component
    if base_name.startswith(('system', 'svc', 'windows', 'ms', 'dwm', 'csrss', 'lsass', 'smss')):
        return True
    
    return False

def categorize_application(app_name):
    """Categorize application based on name"""
    categories = {
        'video': ['vlc', 'netflix', 'youtube', 'mpv', 'kodi', 'mediaplayer', 'movies', 'tv'],
        'meeting': ['zoom', 'teams', 'skype', 'meet', 'webex', 'goto', 'bluejeans'],
        'email': ['thunderbird', 'outlook', 'mail', 'mailspring', 'spark'],
        'work': ['word', 'excel', 'powerpoint', 'libreoffice', 'code', 'vscode', 'pycharm', 
                'intellij', 'eclipse', 'netbeans', 'atom', 'sublime', 'notepad++', 'vim',
                'onenote', 'evernote', 'notion'],
        'social': ['discord', 'slack', 'telegram', 'whatsapp', 'signal', 'messenger', 'teams'],
        'browsing': ['chrome', 'firefox', 'edge', 'safari', 'brave', 'opera', 'vivaldi', 'browser'],
        'streaming': ['spotify', 'apple music', 'pandora', 'soundcloud', 'tidal', 'deezer']
    }
    
    app_name_lower = app_name.lower()
    for category, keywords in categories.items():
        if any(keyword in app_name_lower for keyword in keywords):
            return category
    
    return 'other'

def calculate_energy(category, duration, cpu_usage=0):
    """Calculate energy consumption in kWh"""
    # Base energy rates per hour (kWh)
    energy_rates = {
        'video': 0.15,
        'meeting': 0.12,
        'browsing': 0.03,
        'social': 0.05,
        'email': 0.02,
        'work': 0.06,
        'streaming': 0.08,
        'cloud': 0.08,
        'other': 0.04
    }
    
    base_rate = energy_rates.get(category, energy_rates['other'])
    hours = duration / 3600
    
    # Scale by CPU usage (normalized)
    cpu_multiplier = 1 + (cpu_usage / 100) * 0.5  # Up to 50% increase
    
    return hours * base_rate * cpu_multiplier

def track_system_activity():
    """Background thread to track system applications"""
    global last_activity_time, is_idle
    
    process_start_times = {}
    
    print("🔍 Application tracking started (system processes excluded)")
    
    while config['tracking_enabled']:
        try:
            current_time = time.time()
            
            # Check for idle state
            idle_time = current_time - last_activity_time
            is_idle = idle_time > config['idle_threshold']
            
            if is_idle:
                time.sleep(5)
                continue
            
            # Get all running processes
            current_processes = {}
            
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info['name']
                    pid = proc_info['pid']
                    
                    # Skip if it's a system process
                    if is_system_process(proc_name):
                        continue
                    
                    current_processes[pid] = {
                        'name': proc_name,
                        'cpu': proc_info['cpu_percent']
                    }
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Track new processes
            for pid, info in current_processes.items():
                if pid not in process_start_times:
                    process_start_times[pid] = current_time
                    print(f"✅ Tracking: {info['name']}")
            
            # Calculate duration for ended processes
            ended_pids = set(process_start_times.keys()) - set(current_processes.keys())
            for pid in ended_pids:
                start_time = process_start_times[pid]
                duration = current_time - start_time
                
                if pid in tracked_processes:
                    proc_name = tracked_processes[pid]['name']
                    cpu_usage = tracked_processes[pid].get('cpu', 0)
                    
                    category = categorize_application(proc_name)
                    
                    if proc_name not in activity_data:
                        activity_data[proc_name] = {
                            'total_time': 0,
                            'cpu_usage': 0,
                            'category': category,
                            'last_update': None,
                            'source': 'application'
                        }
                    
                    activity_data[proc_name]['total_time'] += duration
                    activity_data[proc_name]['cpu_usage'] = cpu_usage
                    activity_data[proc_name]['last_update'] = datetime.now().isoformat()
                    
                    print(f"📊 Tracked: {proc_name} for {duration:.0f}s")
                
                del process_start_times[pid]
            
            # Update tracked processes
            tracked_processes.clear()
            tracked_processes.update({pid: info for pid, info in current_processes.items()})
            
            time.sleep(5)  # Check every 5 seconds
            
        except Exception as e:
            print(f"⚠️ Error in tracking: {e}")
            time.sleep(5)

@app.route('/api/activity', methods=['POST'])
def add_activity():
    """Receive activity data from browser extension"""
    data = request.json
    
    source = data.get('source', 'browser')
    identifier = data.get('domain') or data.get('application')
    duration = data.get('duration', 0)
    category = data.get('category', 'unknown')
    
    if identifier not in activity_data:
        activity_data[identifier] = {
            'total_time': 0,
            'cpu_usage': 0,
            'category': category,
            'last_update': None,
            'source': source
        }
    
    activity_data[identifier]['total_time'] += duration
    activity_data[identifier]['last_update'] = datetime.now().isoformat()
    
    # Update last activity time
    global last_activity_time
    last_activity_time = time.time()
    
    return jsonify({'status': 'success'}), 200

@app.route('/api/manual-activity', methods=['POST'])
def add_manual_activity():
    """Receive manual activity data from dashboard"""
    data = request.json
    
    # Store manual activities with their calculated CO2
    for activity_type, activity_data_item in data.items():
        if activity_type in ['email', 'video', 'streaming', 'cloud']:
            identifier = f'manual_{activity_type}_input'
            
            activity_data[identifier] = {
                'total_time': 0,
                'cpu_usage': 0,
                'category': activity_type,
                'last_update': datetime.now().isoformat(),
                'source': 'manual_input',
                'co2': activity_data_item.get('co2', 0),
                'details': activity_data_item
            }
    
    return jsonify({'status': 'success'}), 200

@app.route('/api/calculate', methods=['GET'])
def calculate_footprint():
    """Calculate total carbon footprint including manual inputs"""
    total_energy = 0
    total_co2 = 0
    breakdown = []
    
    for identifier, data in activity_data.items():
        # Check if this is manual input
        if data['source'] == 'manual_input':
            co2 = data.get('co2', 0)
            energy = 0  # Manual inputs already have CO2 calculated
        else:
            # Normal automatic tracking
            energy = calculate_energy(
                data['category'],
                data['total_time'],
                data.get('cpu_usage', 0)
            )
            co2 = energy * config['emission_factor']
        
        total_energy += energy
        total_co2 += co2
        
        breakdown.append({
            'name': identifier,
            'category': data['category'],
            'time': data['total_time'],
            'energy': energy,
            'co2': co2,
            'source': data['source'],
            'details': data.get('details', {})
        })
    
    breakdown.sort(key=lambda x: x['co2'], reverse=True)
    
    if total_co2 < 1:
        status = 'Low'
    elif total_co2 < 5:
        status = 'Moderate'
    elif total_co2 < 10:
        status = 'High'
    else:
        status = 'Very High'
    
    return jsonify({
        'total_energy': total_energy,
        'total_co2': total_co2,
        'status': status,
        'breakdown': breakdown
    })

@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    """Get or update configuration"""
    if request.method == 'POST':
        data = request.json
        config.update(data)
        return jsonify({'status': 'success', 'config': config})
    
    return jsonify(config)

@app.route('/api/reset', methods=['POST'])
def reset_data():
    """Reset all tracking data"""
    activity_data.clear()
    return jsonify({'status': 'success'})

@app.route('/api/reset-manual', methods=['POST'])
def reset_manual_data():
    """Reset only manual input data"""
    keys_to_remove = [k for k in activity_data.keys() if 'manual_' in k and '_input' in k]
    for key in keys_to_remove:
        del activity_data[key]
    
    return jsonify({'status': 'success'})

@app.route('/dashboard')
def dashboard():
    """Serve dashboard HTML"""
    return render_template('dashboard.html')

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """Receive heartbeat to track activity"""
    global last_activity_time
    last_activity_time = time.time()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    # Start background tracking thread
    tracking_thread = threading.Thread(target=track_system_activity, daemon=True)
    tracking_thread.start()
    
    print("\n" + "="*50)
    print("🌍 Carbon Footprint Tracker Started")
    print("="*50)
    print("📊 Dashboard: http://localhost:5000/dashboard")
    print("🔍 Tracking: User applications only")
    print("="*50 + "\n")
    
    # Run Flask app
    app.run(debug=True, port=5000)