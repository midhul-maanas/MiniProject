from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psutil
import time
import threading
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Global data storage
activity_data = defaultdict(lambda: {
    'total_time': 0,
    'cpu_usage': 0,
    'category': 'unknown',
    'last_update': None,
    'source': None,
    'status': 'completed'  # NEW: 'running' or 'completed'
})

config = {
    'emission_factor': 0.475,
    'tracking_enabled': True,
    'idle_threshold': 300,
    'min_cpu_for_active': 0.1,
    'realtime_update_interval': 30  # NEW: Update dashboard every 30 seconds
}

# Process tracking
tracked_processes = {}
process_activity_times = {}
last_activity_time = time.time()
is_idle = False

# System processes blacklist
SYSTEM_PROCESSES_BLACKLIST = {
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
    'systemsettings.exe', 'settingssynchost.exe', 'useroobebroker.exe',
    'msmpeng.exe', 'nissrv.exe', 'securityhealthsystray.exe',
    'securityhealthservice.exe', 'windefend.exe', 'mpcmdrun.exe',
    'wuauclt.exe', 'trustedinstaller.exe', 'tiworker.exe', 'usoclient.exe',
    'musnotification.exe', 'musnotificationux.exe',
    'dashost.exe', 'netsh.exe', 'ping.exe', 'ipconfig.exe',
    'nvdisplay.container.exe', 'nvcontainer.exe', 'nvprofileupdater.exe',
    'atieclxx.exe', 'atiesrxx.exe', 'igfxem.exe', 'igfxpers.exe',
    'igfxtray.exe', 'hkcmd.exe', 'igfxsrvc.exe',
    'kernel_task', 'launchd', 'loginwindow', 'windowserver', 'dock',
    'finder', 'systemuiserver', 'coreaudiod', 'corespotlightd', 'mds',
    'mds_stores', 'mdworker', 'trustd', 'securityd', 'parentalcontrolsd',
    'softwareupdated', 'notifyd', 'distnoted', 'cfprefsd', 'useractivityd',
    'bird', 'cloudd', 'apsd', 'rapportd', 'airplayuiagent',
    'systemd', 'init', 'kthreadd', 'ksoftirqd', 'kworker', 'kswapd',
    'migration', 'watchdog', 'cpuhp', 'kdevtmpfs', 'netns', 'khungtaskd',
    'oom_reaper', 'writeback', 'kcompactd', 'kblockd', 'kintegrityd',
    'idle', 'system32', 'syswow64', 'backgroundtaskhost.exe',
    'taskmgr.exe', 'perfmon.exe', 'resmon.exe', 'mmc.exe',
}

SYSTEM_PROCESS_PATTERNS = [
    'windows', 'microsoft', 'update', 'defender', 'system',
    'svc', 'host', 'service', 'driver', 'helper', 'agent',
    'daemon', 'background', 'runtime', 'broker', 'protocol'
]

def is_system_process(process_name):
    if not process_name:
        return True
    
    process_lower = process_name.lower()
    
    if process_lower in SYSTEM_PROCESSES_BLACKLIST:
        return True
    
    base_name = process_lower.replace('.exe', '').replace('.app', '').replace('.bin', '')
    
    if base_name in SYSTEM_PROCESSES_BLACKLIST:
        return True
    
    pattern_matches = sum(1 for pattern in SYSTEM_PROCESS_PATTERNS if pattern in base_name)
    if pattern_matches >= 2:
        return True
    
    if base_name.startswith(('system', 'svc', 'windows', 'ms', 'dwm', 'csrss', 'lsass', 'smss')):
        return True
    
    return False

def categorize_application(app_name):
    categories = {
        'video': ['vlc', 'netflix', 'youtube', 'mpv', 'kodi', 'mediaplayer', 'movies', 'tv'],
        'meeting': ['zoom', 'teams', 'skype', 'meet', 'webex', 'goto', 'bluejeans'],
        'email': ['thunderbird', 'outlook', 'mail', 'mailspring', 'spark'],
        'work': ['word', 'excel', 'powerpoint', 'libreoffice', 'code', 'vscode', 'pycharm', 
                'intellij', 'eclipse', 'netbeans', 'atom', 'sublime', 'notepad++', 'vim',
                'onenote', 'evernote', 'notion'],
        'social': ['discord', 'slack', 'telegram', 'whatsapp', 'signal', 'messenger'],
        'browsing': ['chrome', 'firefox', 'edge', 'safari', 'brave', 'opera', 'vivaldi', 'browser'],
        'streaming': ['spotify', 'apple music', 'pandora', 'soundcloud', 'tidal', 'deezer', 'music'],
        'design': ['paint', 'mspaint', 'photoshop', 'illustrator', 'figma', 'sketch', 'canva', 'gimp']
    }
    
    app_name_lower = app_name.lower()
    for category, keywords in categories.items():
        if any(keyword in app_name_lower for keyword in keywords):
            return category
    
    return 'other'

def calculate_energy(category, duration, cpu_usage=0):
    energy_rates = {
        'video': 0.15,
        'meeting': 0.12,
        'browsing': 0.03,
        'social': 0.05,
        'email': 0.02,
        'work': 0.06,
        'streaming': 0.08,
        'cloud': 0.08,
        'design': 0.05,
        'other': 0.04
    }
    
    base_rate = energy_rates.get(category, energy_rates['other'])
    hours = duration / 3600
    cpu_multiplier = 1 + (cpu_usage / 100) * 0.5
    
    return hours * base_rate * cpu_multiplier

def update_realtime_data():
    """✅ NEW: Update activity_data with current running apps"""
    for pid, proc_data in process_activity_times.items():
        proc_name = proc_data['name']
        active_time = proc_data['active_time']
        avg_cpu = proc_data['total_cpu'] / proc_data['checks'] if proc_data['checks'] > 0 else 0
        
        if active_time > 0:
            category = categorize_application(proc_name)
            
            activity_data[proc_name] = {
                'total_time': active_time,
                'cpu_usage': avg_cpu,
                'category': category,
                'last_update': datetime.now().isoformat(),
                'source': 'application',
                'status': 'running'  # ✅ Mark as currently running
            }

def track_system_activity():
    """Track active application time with real-time updates"""
    global last_activity_time, is_idle, process_activity_times
    
    print("🔍 Application tracking started (system processes excluded)")
    print("⏱️  Real-time tracking enabled (updates every 30s)")
    print("📊 Tracking ACTIVE time only (CPU > 0.1%)\n")
    
    last_realtime_update = time.time()
    
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
                    cpu = proc_info['cpu_percent']
                    
                    if is_system_process(proc_name):
                        continue
                    
                    current_processes[pid] = {
                        'name': proc_name,
                        'cpu': cpu
                    }
                    
                    # Track activity time based on CPU usage
                    if pid not in process_activity_times:
                        process_activity_times[pid] = {
                            'name': proc_name,
                            'active_time': 0,
                            'last_check': current_time,
                            'total_cpu': 0,
                            'checks': 0
                        }
                    
                    # Count this interval if app is active
                    if cpu > config['min_cpu_for_active']:
                        time_since_last = current_time - process_activity_times[pid]['last_check']
                        process_activity_times[pid]['active_time'] += time_since_last
                    
                    process_activity_times[pid]['last_check'] = current_time
                    process_activity_times[pid]['total_cpu'] += cpu
                    process_activity_times[pid]['checks'] += 1
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # ✅ NEW: Real-time update every 30 seconds
            if current_time - last_realtime_update >= config['realtime_update_interval']:
                update_realtime_data()
                print(f"📊 Real-time update at {datetime.now().strftime('%H:%M:%S')}")
                last_realtime_update = current_time
            
            # Save data for processes that ended
            ended_pids = set(process_activity_times.keys()) - set(current_processes.keys())
            for pid in ended_pids:
                proc_data = process_activity_times[pid]
                proc_name = proc_data['name']
                active_time = proc_data['active_time']
                avg_cpu = proc_data['total_cpu'] / proc_data['checks'] if proc_data['checks'] > 0 else 0
                
                if active_time > 0:
                    category = categorize_application(proc_name)
                    
                    # Update with final values and mark as completed
                    activity_data[proc_name] = {
                        'total_time': activity_data[proc_name].get('total_time', 0) + active_time,
                        'cpu_usage': avg_cpu,
                        'category': category,
                        'last_update': datetime.now().isoformat(),
                        'source': 'application',
                        'status': 'completed'  # ✅ Mark as completed
                    }
                    
                    print(f"✅ Completed: {proc_name}")
                    print(f"   Active time: {active_time:.0f}s ({active_time/60:.1f} min)")
                    print(f"   Average CPU: {avg_cpu:.1f}%")
                    print(f"   Category: {category}\n")
                
                del process_activity_times[pid]
            
            # Update tracked processes
            tracked_processes.clear()
            tracked_processes.update({pid: info for pid, info in current_processes.items()})
            
            time.sleep(5)
            
        except Exception as e:
            print(f"⚠️ Error in tracking: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)

@app.route('/api/activity', methods=['POST'])
def add_activity():
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
            'source': source,
            'status': 'completed'
        }
    
    activity_data[identifier]['total_time'] += duration
    activity_data[identifier]['last_update'] = datetime.now().isoformat()
    
    global last_activity_time
    last_activity_time = time.time()
    
    return jsonify({'status': 'success'}), 200

@app.route('/api/manual-activity', methods=['POST'])
def add_manual_activity():
    data = request.json
    
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
                'details': activity_data_item,
                'status': 'completed'
            }
    
    return jsonify({'status': 'success'}), 200

@app.route('/api/calculate', methods=['GET'])
def calculate_footprint():
    total_energy = 0
    total_co2 = 0
    breakdown = []
    
    for identifier, data in activity_data.items():
        if data['source'] == 'manual_input':
            co2 = data.get('co2', 0)
            energy = 0
        else:
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
            'status': data.get('status', 'completed'),  # ✅ Include status
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
    if request.method == 'POST':
        data = request.json
        config.update(data)
        return jsonify({'status': 'success', 'config': config})
    
    return jsonify(config)

@app.route('/api/reset', methods=['POST'])
def reset_data():
    activity_data.clear()
    return jsonify({'status': 'success'})

@app.route('/api/reset-manual', methods=['POST'])
def reset_manual_data():
    keys_to_remove = [k for k in activity_data.keys() if 'manual_' in k and '_input' in k]
    for key in keys_to_remove:
        del activity_data[key]
    
    return jsonify({'status': 'success'})

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    global last_activity_time
    last_activity_time = time.time()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    tracking_thread = threading.Thread(target=track_system_activity, daemon=True)
    tracking_thread.start()
    
    print("\n" + "="*60)
    print("🌍 Carbon Footprint Tracker Started (Real-Time Edition)")
    print("="*60)
    print("📊 Dashboard: http://localhost:5000/dashboard")
    print("🔍 Tracking: Active application time only (CPU-based)")
    print("⏱️  Updates: Every 30 seconds (real-time)")
    print("📈 Running apps show live CO₂ values")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000)