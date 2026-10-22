#!/usr/bin/env python3
"""Deploy the portal with private credentials; optionally install GitHub App config."""
import argparse
import base64
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parent.parent
K = str(ROOT / 'scripts/kubectl')

def call(*args, data=None):
    return subprocess.run([K, *args], input=json.dumps(data) if data else None,
                          text=True, check=True, capture_output=True).stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True, help='Published ghcr.io/naiin/devplatform-backstage image with immutable digest')
    parser.add_argument('--github-config', type=Path, help='Private local GitHub App YAML; never commit it')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'ghcr.io/naiin/(devplatform-backstage|devplatformdeveloper-api)@sha256:[0-9a-f]{64}', args.image):
        parser.error('Provide the immutable published portal image digest')
    call('apply', '-f', '-', data={'apiVersion':'v1','kind':'Namespace','metadata':{'name':'backstage','labels':{'pod-security.kubernetes.io/enforce':'restricted'}}})
    exists = subprocess.run([K,'-n','backstage','get','secret','backstage-credentials'],capture_output=True).returncode == 0
    if not exists:
        call('create','-f','-', data={'apiVersion':'v1','kind':'Secret','metadata':{'name':'backstage-credentials','namespace':'backstage'},
            'stringData':{'POSTGRES_PASSWORD':secrets.token_hex(32),'GITHUB_TOKEN':''}})
    if args.github_config:
        config = args.github_config.read_text()
        if 'REPLACE_' in config:
            parser.error('Complete the private GitHub App config before installing it')
    else:
        config = 'integrations:\n  github:\n    - host: github.com\n'
    existing = subprocess.run([K,'-n','backstage','get','secret','backstage-github'],capture_output=True).returncode == 0
    if args.github_config or not existing:
        call('apply','-f','-', data={'apiVersion':'v1','kind':'Secret','metadata':{'name':'backstage-github','namespace':'backstage'},
            'data':{'github.yaml':base64.b64encode(config.encode()).decode()}})
    call('apply','-f',str(ROOT/'gitops/backstage/resources.yaml'))
    patch = {'spec':{'template':{'spec':{'containers':[{'name':'backstage','image':args.image}]}}}}
    call('-n','backstage','patch','deployment','backstage','--type','strategic','-p',json.dumps(patch))
    call('-n','backstage','rollout','restart','deployment/backstage')
    print('Backstage resources applied; waiting for the portal.')
    subprocess.run([K,'-n','backstage','rollout','status','deployment/backstage','--timeout=300s'],check=True)
    print('Portal: http://demo.talos.test/backstage — GitHub configuration is required to create services.')

if __name__ == '__main__':
    main()
