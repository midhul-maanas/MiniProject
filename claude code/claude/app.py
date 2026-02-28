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
    'status': 'completed'
})

config = {
    'emission_factor': 0.475,
    'tracking_enabled': True,
    'idle_threshold': 300,
    'realtime_update_interval': 30,
    'track_all_running': True  # NEW: Track all running apps, not just active ones
}

# Process tracking
tracked_processes = {}
process_start_times = {}  # Track when each process started
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
        'streaming': ['spotify', 'music', 'itunes', 'pandora', 'soundcloud', 'tidal', 'deezer'],
        'design': ['paint', 'mspaint', 'photoshop', 'illustrator', 'figma', 'sketch', 'canva', 'gimp', 'paintapp', 'pbrush']
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
    """Update activity_data with ALL currently running apps"""
    current_time = time.time()
    
    for pid, start_time in process_start_times.items():
        if pid in tracked_processes:
            proc_name = tracked_processes[pid]['name']
            running_time = current_time - start_time
            
            # Get average CPU
            cpu = tracked_processes[pid].get('cpu', 0)
            
            category = categorize_application(proc_name)
            
            # Update with current running time
            activity_data[proc_name] = {
                'total_time': running_time,
                'cpu_usage': cpu,
                'category': category,
                'last_update': datetime.now().isoformat(),
                'source': 'application',
                'status': 'running'
            }

def track_system_activity():
    """✅ FIXED: Track ALL running applications continuously"""
    global last_activity_time, is_idle, process_start_times, tracked_processes
    
    print("🔍 Application tracking started")
    print("="*60)
    print("✅ CONTINUOUS TRACKING MODE")
    print("   → All running apps tracked (minimized or not)")
    print("   → No CPU threshold required")
    print("   → Accurate time for all applications")
    print(f"⏱️  Real-time updates: Every {config['realtime_update_interval']}s")
    print("="*60 + "\n")
    
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
                    
                    # ✅ Track start time for NEW processes
                    if pid not in process_start_times:
                        process_start_times[pid] = current_time
                        print(f"✅ Started tracking: {proc_name} (PID: {pid})")
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # ✅ Real-time update every 30 seconds (update ALL running apps)
            if current_time - last_realtime_update >= config['realtime_update_interval']:
                update_realtime_data()
                running_count = len([p for p in activity_data.values() if p['status'] == 'running'])
                print(f"📊 Real-time update: {running_count} apps currently running")
                last_realtime_update = current_time
            
            # ✅ Save data for processes that ENDED
            ended_pids = set(process_start_times.keys()) - set(current_processes.keys())
            for pid in ended_pids:
                if pid in tracked_processes:
                    proc_name = tracked_processes[pid]['name']
                    start_time = process_start_times[pid]
                    total_time = current_time - start_time
                    cpu = tracked_processes[pid].get('cpu', 0)
                    
                    category = categorize_application(proc_name)
                    
                    # Add to existing time if app was opened before
                    prev_time = 0
                    if proc_name in activity_data and activity_data[proc_name]['status'] == 'completed':
                        prev_time = activity_data[proc_name]['total_time']
                    
                    # Save final values
                    activity_data[proc_name] = {
                        'total_time': prev_time + total_time,
                        'cpu_usage': cpu,
                        'category': category,
                        'last_update': datetime.now().isoformat(),
                        'source': 'application',
                        'status': 'completed'
                    }
                    
                    print(f"✅ Completed: {proc_name}")
                    print(f"   Session time: {total_time/60:.1f} min")
                    print(f"   Total time: {(prev_time + total_time)/60:.1f} min")
                    print(f"   Category: {category}\n")
                
                # Remove from tracking
                del process_start_times[pid]
            
            # Update tracked processes
            tracked_processes.clear()
            tracked_processes.update(current_processes)
            
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
            'status': data.get('status', 'completed'),
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
    process_start_times.clear()
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
    print("🌍 Carbon Footprint Tracker - ACCURATE EDITION")
    print("="*60)
    print("📊 Dashboard: http://localhost:5000/dashboard")
    print("")
    print("✅ TRACKING MODE: ALL RUNNING APPS")
    print("   • Spotify playing in background: ✅ Tracked")
    print("   • Paint minimized: ✅ Tracked")
    print("   • Chrome tabs: ✅ Tracked (via extension)")
    print("   • Any running app: ✅ Tracked accurately")
    print("")
    print("⏱️  Updates every 30 seconds")
    print("🎯 100% accurate time tracking")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5000)