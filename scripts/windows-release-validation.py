"""Windows-only frozen/installed synthetic API validation; never a GUI proof."""
import argparse, hashlib, http.cookiejar, io, json, os, re, secrets, socket
import subprocess, sys, tempfile, time, urllib.error, urllib.request
from datetime import date
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps_json(command):
    raw = subprocess.check_output(['powershell', '-NoProfile', '-NonInteractive', '-Command', command], text=True, timeout=30).strip()
    return json.loads(raw) if raw else None


def no_existing_app():
    rows = ps_json("@(Get-CimInstance Win32_Process -Filter \"Name='FlowBooks.exe'\" | Select-Object ProcessId) | ConvertTo-Json -Compress")
    if rows:
        raise RuntimeError('Existing FlowBooks process; refuse installer/test collision')


def call(opener, base, method, path, expected, payload=None, pdf=False):
    headers = {'Content-Type': 'application/json'} if payload is not None else {}
    req = urllib.request.Request(base+path, data=None if payload is None else json.dumps(payload).encode(), headers=headers, method=method)
    try:
        response = opener.open(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    if response.status != expected:
        # Never echo response/request bodies, cookies or passwords.
        raise RuntimeError(f'{method} {path}: expected {expected}, got {response.status}')
    if pdf:
        if not body.startswith(b'%PDF-') or len(body) < 1000 or response.headers.get_content_type() != 'application/pdf':
            raise RuntimeError('Business PDF signature/size/content-type failed')
        return body
    return json.loads(body) if body else None


def run_case(exe, root, currency, records):
    no_existing_app()
    data = root / 'data'; data.mkdir()
    password = secrets.token_urlsafe(32)  # memory only; app stores its normal hash
    company = 'Windows Synthetic '+currency
    env = dict(os.environ)
    for name in ['DATABASE_URL','SLOWBOOKS_ENV_FILE','SLOWBOOKS_DATA_DIR','SESSION_SECRET_KEY','SETTINGS_ENCRYPTION_KEY','PAYROLL_ENCRYPTION_SECRET','APP_PORT','CORS_ALLOW_ORIGINS']:
        env.pop(name,None)
    env['SLOWBOOKS_DATA_DIR'] = str(data)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    bare = urllib.request.build_opener()
    today = date.today().isoformat()
    period = f'start_date={today}&end_date={today}'
    setup_complete = False
    own_pids = []
    for iteration in range(2):
        proc = subprocess.Popen([str(exe),'--no-window','--data-dir',str(data),'--port',str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cleanup = {'launcher_pid':proc.pid,'iteration':iteration,'forced_pid_tree_fallback':False}
        try:
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('Owned frozen launcher exited before health')
                try:
                    health = call(bare,base,'GET','/health',200)
                    break
                except (OSError,urllib.error.URLError):
                    time.sleep(.5)
            else:
                raise RuntimeError('Owned frozen health timeout')
            if health.get('version') != '2.21.0':
                raise RuntimeError('Unexpected app version')
            processes = ps_json("@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath) | ConvertTo-Json -Compress") or []
            own_pids = [proc.pid]
            for _ in range(5):
                own_pids = sorted(set(own_pids+[int(r['ProcessId']) for r in processes if int(r['ParentProcessId']) in own_pids]))
            listener = ps_json(f"@(Get-NetTCPConnection -State Listen -LocalPort {port} | Select-Object OwningProcess) | ConvertTo-Json -Compress")
            listeners = listener if isinstance(listener,list) else [listener] if listener else []
            if not listeners or any(int(r['OwningProcess']) not in own_pids for r in listeners):
                raise RuntimeError('Listener is not an owned frozen descendant')
            dbs = list((data/'companies').glob('*.db'))
            if len(dbs) != 1:
                raise RuntimeError('Expected exactly one newly created synthetic company DB')
            records.append({'scope':root.name,'iteration':iteration,'ownership':{'launcher_pid':proc.pid,'owned_process_ids':own_pids,'company_db_relative':str(dbs[0].relative_to(data)),'listener_owned':True},'version':health['version']})
            admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            if not setup_complete:
                status = call(bare,base,'GET','/api/auth/status',200)
                if status.get('home_currency') != 'ZAR' or not status.get('can_choose_home_currency'):
                    raise RuntimeError('New-company default/choice contract failed')
                payload = {'password':password,'company_name':company}
                if currency == 'USD': payload['home_currency'] = 'USD'
                call(admin,base,'POST','/api/auth/setup',200,payload)
                setup_complete = True
            # Fresh no-cookie opener proves wrong password denial after setup/restart.
            call(bare,base,'POST','/api/auth/login',401,{'password':secrets.token_urlsafe(32)})
            call(admin,base,'POST','/api/auth/login',200,{'password':password})
            settings = call(admin,base,'GET','/api/settings',200)
            if settings.get('company_name') != company or settings.get('home_currency') != currency:
                raise RuntimeError('Company/currency identity or restart persistence failed')
            if iteration == 0:
                customer = call(admin,base,'POST','/api/customers',201,{'name':'Synthetic Windows Customer'})
                invoice = call(admin,base,'POST','/api/invoices',201,{'customer_id':customer['id'],'date':today,'tax_rate':'0','currency':currency,'lines':[{'description':'Synthetic validation service','quantity':'1','rate':'123.45','amount':'123.45'}]})
                invoice_id = invoice['id']
            pl = call(admin,base,'GET','/api/reports/profit-loss?'+period,200)
            if abs(float(pl['total_income'])-123.45) > .0001:
                raise RuntimeError('Synthetic posted income/restart amount failed')
            pdfs = {}
            for label,path in [('invoice',f'/api/invoices/{invoice_id}/pdf'),('profit_loss','/api/reports/profit-loss/pdf?'+period)]:
                body = call(admin,base,'GET',path,200,pdf=True)
                from pypdf import PdfReader
                text = ' '.join(' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(body)).pages).split())
                money = r'R\s*123\.45' if currency == 'ZAR' else r'\$\s*123\.45'
                if company.casefold() not in text.casefold() or not re.search(money,text):
                    raise RuntimeError('Business PDF company/currency/amount text failed')
                pdfs[label] = {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'company_currency_amount_text':'PASS'}
            records.append({'scope':root.name,'iteration':iteration,'normal_setup_login_wrong401':True,'home_currency':currency,'synthetic_income':pl['total_income'],'business_pdf_http':pdfs,'native_GUI_PDF_viewer':'NOT_RUN','PDF_text_currency_amount':'PASS','PDF_visual_viewer':'NOT_RUN'})
            call(admin,base,'POST','/api/auth/logout',200,{})
        finally:
            # Headless windowless exe can refuse non-force taskkill: record fallback.
            # Never kill by app name or target another process/terminal.
            targets = [proc.pid] if proc.poll() is None else []
            if not targets and own_pids:
                alive = ps_json("@(Get-CimInstance Win32_Process | Select-Object ProcessId,ExecutablePath) | ConvertTo-Json -Compress") or []
                targets = [int(r['ProcessId']) for r in alive if int(r['ProcessId']) in own_pids and r.get('ExecutablePath') and Path(r['ExecutablePath']).resolve() == exe.resolve()]
            cleanup['target_pids'] = targets
            for target in targets:
                stop = subprocess.run(['taskkill','/PID',str(target),'/T'],capture_output=True,timeout=20)
                if stop.returncode != 0:
                    cleanup['forced_pid_tree_fallback'] = True
                    subprocess.run(['taskkill','/PID',str(target),'/T','/F'],capture_output=True,timeout=20,check=True)
            proc.wait(timeout=20)
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1',port)) != 0: break
                time.sleep(.25)
            else:
                raise RuntimeError('Owned backend port still open after PID-tree cleanup')
            records.append({'scope':root.name,'cleanup':cleanup,'port_released':True})
            no_existing_app()
    password = None
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--portable-exe',type=Path,required=True)
    parser.add_argument('--installer',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args = parser.parse_args()
    if sys.platform != 'win32': raise SystemExit('Windows-only proposal; not executable on this host')
    records = []; outcome = {'result':'FAIL','native_GUI':'NOT_RUN','records':records}
    try:
        no_existing_app()
        # New private temp root; no user-company path or shared data directory.
        with tempfile.TemporaryDirectory(prefix='flowbooks-native-validation-',dir=os.environ['RUNNER_TEMP']) as tmp:
            root = Path(tmp)
            for currency in ['ZAR','USD']:
                case = root/('portable-'+currency);case.mkdir()
                run_case(args.portable_exe.resolve(),case,currency,records)
            install = root/'installed';install.mkdir()
            command = [str(args.installer.resolve()),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS',f'/DIR={install}']
            subprocess.run(command,check=True,timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            installed = install/'FlowBooks.exe'
            if not installed.is_file() or digest(installed)!=digest(args.portable_exe):
                raise RuntimeError('Quiet installation payload hash mismatch')
            if (install/'LICENSE.txt').read_bytes() != Path('LICENSE').read_bytes():
                raise RuntimeError('Installed LICENSE mismatch')
            case = root/'installed-ZAR';case.mkdir()
            data = run_case(installed,case,'ZAR',records)
            before = {str(f.relative_to(data)):digest(f) for f in data.rglob('*.db')}
            subprocess.run([str(install/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=180,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            after = {str(f.relative_to(data)):digest(f) for f in data.rglob('*.db')}
            if not before or before != after or installed.exists():
                raise RuntimeError('Uninstall/data-retention check failed')
            records.append({'quiet_install_payload_SHA_and_LICENSE':'PASS','installed_backend_retested':'PASS','uninstall_preserved_synthetic_DB_SHA':'PASS','native_install_wizard_GUI':'NOT_RUN'})
        outcome['result'] = 'PASS_HTTP_FROZEN_AND_QUIET_INSTALL'
    except Exception as error:
        outcome['failure_type'] = type(error).__name__
        # All raised diagnostic strings avoid input/body/password values.
        outcome['failure'] = str(error)
    finally:
        args.receipt.write_text(json.dumps(outcome,indent=2)+'\n')
    return 0 if outcome['result'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
