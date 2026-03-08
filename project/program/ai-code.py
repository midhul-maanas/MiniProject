from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psutil
import time
import threading
from datetime import datetime
from collections import defaultdict
import win32gui
import win32process


app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Data store
# ---------------------------------------------------------------------------
# Schema per process entry:
#   total_time  – accumulated seconds from COMPLETED sessions only
#   start_time  – time.time() when the current running session began; None when stopped
#   status      – "running" | "completed"
#   cpu_usage   – rolling average CPU %
#   category    – app category string
#   source      – "application" | "browser" | "manual_input"
# ---------------------------------------------------------------------------
activity_data = {}

config = {
    'emission_factor': 0.475,
    'tracking_enabled': True,
    'idle_threshold': 300,
    'realtime_update_interval': 5,
    'track_all_running': True
}

tracked_processes = {}
last_activity_time = time.time()
is_idle = False


# ---------------------------------------------------------------------------
# System process filtering
# ---------------------------------------------------------------------------
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


def window_checked(name):
    """Return True if the process has a visible window (user-facing app)."""
    visible_processes = set()

    def enum_window_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if not win32gui.GetWindowText(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid)
            proc_name = process.name().lower().replace('.exe', '')
            visible_processes.add(proc_name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    win32gui.EnumWindows(enum_window_callback, None)
    base_name = name.lower().replace('.exe', '')
    return base_name in visible_processes


def is_system_process(process_name):
    if not process_name:
        return True
    process_lower = process_name.lower()
    if process_lower in SYSTEM_PROCESSES_BLACKLIST:
        return True
    base_name = process_lower.replace('.exe', '').replace('.app', '').replace('.bin', '')
    if base_name in SYSTEM_PROCESSES_BLACKLIST:
        return True
    pattern_matches = sum(1 for p in SYSTEM_PROCESS_PATTERNS if p in base_name)
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
        'design': ['paint', 'mspaint', 'photoshop', 'illustrator', 'figma', 'sketch',
                    'canva', 'gimp', 'paintapp', 'pbrush']
    }
    app_name_lower = app_name.lower()
    for category, keywords in categories.items():
        if any(kw in app_name_lower for kw in keywords):
            return category
    return 'other'


def calculate_energy(category, duration, cpu_usage=0):
    energy_rates = {
        'video': 0.15, 'meeting': 0.12, 'browsing': 0.03,
        'social': 0.05, 'email': 0.02, 'work': 0.06,
        'streaming': 0.08, 'cloud': 0.08, 'design': 0.05,
        'other': 0.04
    }
    base_rate = energy_rates.get(category, energy_rates['other'])
    hours = duration / 3600
    cpu_multiplier = 1 + (cpu_usage / 100) * 0.5
    return hours * base_rate * cpu_multiplier


# ---------------------------------------------------------------------------
# Helper: compute live runtime for a single activity_data entry
# ---------------------------------------------------------------------------
def _live_time(data):
    """Return the real-time runtime in seconds for a tracked application.

    Computes: total_time + (now - start_time) - idle_total - current_idle.
    Idle periods are subtracted so the session is never broken; the
    dashboard always gets a valid, continuously-increasing number for
    active apps and a frozen-but-valid number for idle apps.
    """
    now = time.time()
    total = data.get('total_time', 0)

    if data.get('start_time') is not None:
        runtime = now - data['start_time']
        runtime -= data.get('idle_total', 0)
        if data.get('idle_start') is not None:
            runtime -= now - data['idle_start']
        total += max(runtime, 0)

    return total


# ---------------------------------------------------------------------------
# Background tracking loop
# ---------------------------------------------------------------------------
def track_system_activity():
    """Track running desktop applications every 5 seconds.

    Uses a start_time-based model:
      • When a process is first seen  → record start_time, status = "running"
      • While it keeps running        → only update cpu_usage (time is computed on-the-fly)
      • When it disappears            → total_time += (now - start_time), clear start_time
    """
    global last_activity_time, is_idle, tracked_processes

    print("🔍 Application tracking started")
    print("=" * 60)
    print("✅ CUMULATIVE TRACKING MODE (start_time-based)")
    print("   → Live time computed on-the-fly in /api/calculate")
    print("   → Sessions accumulate correctly across restarts")
    print(f"⏱️  Polling interval: Every {config['realtime_update_interval']}s")
    print(f"😴 Idle threshold: {config['idle_threshold']}s ({config['idle_threshold']/60:.0f} min)")
    print("=" * 60 + "\n")

    while config['tracking_enabled']:
        try:
            current_time = time.time()

            # ------ Detect foreground (active) application ------
            try:
                hwnd = win32gui.GetForegroundWindow()
                _, active_pid = win32process.GetWindowThreadProcessId(hwnd)
                active_app = psutil.Process(active_pid).name()
            except Exception:
                active_app = None

            # ------ Snapshot currently visible processes ------
            current_processes = {}
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info['name']
                    pid = proc_info['pid']
                    cpu = proc_info['cpu_percent'] or 0

                    if is_system_process(proc_name):
                        continue
                    if not window_checked(proc_name):
                        continue

                    current_processes[pid] = {
                        'name': proc_name,
                        'cpu': cpu,
                    }

                    category = categorize_application(proc_name)

                    if proc_name not in activity_data:
                        # ---- First time seeing this process ----
                        activity_data[proc_name] = {
                            'total_time': 0,
                            'start_time': current_time,
                            'cpu_usage': cpu,
                            'category': category,
                            'source': 'application',
                            'status': 'running',
                            'last_active': current_time,
                            'app_idle': False,
                            'idle_start': None,
                            'idle_total': 0,
                        }
                    else:
                        entry = activity_data[proc_name]
                        if entry['status'] == 'completed':
                            # ---- Process restarted: begin a new session ----
                            entry['start_time'] = current_time
                            entry['status'] = 'running'
                            entry['last_active'] = current_time
                            entry['app_idle'] = False
                            entry['idle_start'] = None
                            entry['idle_total'] = 0
                        # Update rolling average CPU (keep it cheap)
                        entry['cpu_usage'] = (entry['cpu_usage'] + cpu) / 2

                    # ---- Update idle state for this process ----
                    entry = activity_data[proc_name]

                    # Foreground app is always active
                    if active_app and proc_name == active_app:
                        entry['last_active'] = current_time

                    idle_time = current_time - entry.get('last_active', current_time)

                    # Streaming/video apps should never become idle
                    if entry.get('category') in ('streaming', 'video'):
                        entry['app_idle'] = False
                    else:
                        entry['app_idle'] = idle_time > config['idle_threshold']

                    # Set status indicator (does NOT affect session tracking)
                    if entry['app_idle']:
                        entry['status'] = 'idle'
                        # Record when idle period started (once)
                        if entry.get('idle_start') is None:
                            entry['idle_start'] = current_time
                    else:
                        # Resume from idle: accumulate idle duration, clear marker
                        if entry.get('idle_start') is not None:
                            entry['idle_total'] = entry.get('idle_total', 0) + (current_time - entry['idle_start'])
                            entry['idle_start'] = None
                        entry['status'] = 'running'

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # ------ Detect processes that stopped ------
            ended_pids = set(tracked_processes.keys()) - set(current_processes.keys())
            for pid in ended_pids:
                proc_name = tracked_processes[pid]['name']
                if proc_name in activity_data:
                    entry = activity_data[proc_name]
                    if entry.get('status') in ('running', 'idle') and entry.get('start_time') is not None:
                        # Finalize the session: subtract idle time from duration
                        session_duration = current_time - entry['start_time']
                        session_duration -= entry.get('idle_total', 0)
                        if entry.get('idle_start') is not None:
                            session_duration -= current_time - entry['idle_start']
                        entry['total_time'] += max(session_duration, 0)
                        entry['start_time'] = None
                        entry['idle_start'] = None
                        entry['idle_total'] = 0
                        entry['app_idle'] = False
                        entry['status'] = 'completed'
                        print(f"✅ Completed: {proc_name}")
                        print(f"   Total time: {entry['total_time']/60:.1f} min")

            # ------ Refresh tracked_processes for next iteration ------
            tracked_processes.clear()
            tracked_processes.update(current_processes)

            time.sleep(config['realtime_update_interval'])

        except Exception as e:
            print(f"⚠️ Error in tracking: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

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
            'start_time': None,
            'cpu_usage': 0,
            'category': category,
            'source': source,
            'status': 'completed',
        }

    activity_data[identifier]['total_time'] += duration

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
                'start_time': None,
                'cpu_usage': 0,
                'category': activity_type,
                'source': 'manual_input',
                'co2': activity_data_item.get('co2', 0),
                'details': activity_data_item,
                'status': 'completed',
            }

    return jsonify({'status': 'success'}), 200


@app.route('/api/calculate', methods=['GET'])
def calculate_footprint():
    """Return the carbon footprint breakdown with LIVE runtime values.

    For running processes the time includes the current (still-ongoing)
    session, so the dashboard sees a continuously increasing number without
    waiting for the next tracking-loop tick.
    """
    total_energy = 0
    total_co2 = 0
    breakdown = []

    for identifier, data in activity_data.items():
        # --- Compute live time ---
        live_time = _live_time(data)

        if data.get('source') == 'manual_input':
            co2 = data.get('co2', 0)
            energy = 0
        else:
            energy = calculate_energy(
                data['category'],
                live_time,
                data.get('cpu_usage', 0)
            )
            co2 = energy * config['emission_factor']

        total_energy += energy
        total_co2 += co2

        breakdown.append({
            'name': identifier,
            'category': data['category'],
            'time': live_time,
            'energy': energy,
            'co2': co2,
            'source': data.get('source', 'application'),
            'status': data.get('status', 'completed'),
            'app_idle': data.get('app_idle', False),
            'details': data.get('details', {}),
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
        'breakdown': breakdown,
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
    tracked_processes.clear()
    return jsonify({'status': 'success'})


@app.route('/api/reset-manual', methods=['POST'])
def reset_manual_data():
    keys_to_remove = [k for k in activity_data if 'manual_' in k and '_input' in k]
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    tracking_thread = threading.Thread(target=track_system_activity, daemon=True)
    tracking_thread.start()

    print("\n" + "=" * 60)
    print("🌍 Carbon Footprint Tracker – Fixed Cumulative Tracking")
    print("=" * 60)
    print("📊 Dashboard: http://localhost:5000/dashboard")
    print("")
    print("✅ FEATURES:")
    print("   • Real-time live runtime (start_time-based)  ✅")
    print("   • Cumulative across process restarts         ✅")
    print("   • No double-counting or time resets          ✅")
    print("   • Independent of polling frequency           ✅")
    print("")
    print("⏱️  Polling every 5 seconds")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)