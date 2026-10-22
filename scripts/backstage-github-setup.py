#!/usr/bin/env python3
"""Install GitHub App credentials locally without putting secrets in chat or Git."""
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parent.parent
app_id = input('GitHub App ID: ').strip()
client_id = input('GitHub App client ID: ').strip()
client_secret = getpass.getpass('GitHub App client secret (hidden): ').strip()
key_path = Path(input('Path to downloaded private-key PEM: ').strip()).expanduser()
private_key = key_path.read_text()
if not app_id.isdigit() or not client_id or not client_secret or 'PRIVATE KEY-----' not in private_key:
    raise SystemExit('Incomplete GitHub App credentials; nothing installed.')
config = {
    'integrations': {'github': [{'host':'github.com','apps':[{
        'appId':int(app_id),'clientId':client_id,'clientSecret':client_secret,
        'allowedInstallationOwners':['naiin'],'privateKey':private_key,
    }]}]},
    'auth': {'providers': {'github': {'production': {
        'clientId':client_id,'clientSecret':client_secret,
        'signIn':{'resolvers':[{'resolver':'usernameMatchingUserEntityName'}]},
    }}}},
}
path = ROOT / 'generated/backstage-github.yaml'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd,'w') as handle:
    yaml.safe_dump(config, handle, sort_keys=False)
result = subprocess.check_output([str(ROOT/'scripts/kubectl'),'-n','backstage','get','deployment','backstage','-o','json'],text=True)
image = json.loads(result)['spec']['template']['spec']['containers'][0]['image']
subprocess.run([sys.executable,str(ROOT/'scripts/backstage-bootstrap.py'),'--image',image,'--github-config',str(path)],check=True)
print('GitHub App installed. Open the portal and sign in through GitHub as naiin.')
