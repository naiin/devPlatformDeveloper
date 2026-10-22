#!/usr/bin/env python3
"""Prepare one reviewed service's isolated credentials before merging its onboarding PR."""
import argparse
import json
from pathlib import Path
import re
import secrets
import subprocess

K = str(Path(__file__).resolve().parent / 'kubectl')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('service')
args = parser.parse_args()
if not re.fullmatch(r'[a-z][a-z0-9-]{2,30}', args.service) or args.service in {'platform','hello'}:
    parser.error('Choose a unique generated service name, excluding platform and hello')
namespace = f'staging-{args.service}'

def apply(obj):
    subprocess.run([K,'apply','-f','-'],input=json.dumps(obj),text=True,check=True,capture_output=True)

exists = subprocess.run([K,'get','namespace',namespace,'-o','json'],capture_output=True,text=True)
if exists.returncode == 0:
    ns = json.loads(exists.stdout)
    if ns['metadata'].get('labels',{}).get('devplatform.io/managed-by') != 'backstage-onboarding':
        raise SystemExit('Refusing to adopt an existing namespace without an onboarding ownership label')
else:
    apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,'labels':{
        'pod-security.kubernetes.io/enforce':'restricted','devplatform.io/managed-by':'backstage-onboarding'}}})
exists = subprocess.run([K,'-n',namespace,'get','secret','platform-credentials'],capture_output=True).returncode == 0
if exists:
    print(f'{namespace}: preserving existing database credentials')
else:
    postgres,redis = secrets.token_hex(24),secrets.token_hex(24)
    obj={'apiVersion':'v1','kind':'Secret','metadata':{'name':'platform-credentials','namespace':namespace},'stringData':{
        'POSTGRES_PASSWORD':postgres,'REDIS_PASSWORD':redis,
        'DATABASE_URL':f'postgresql+psycopg://platform:{postgres}@platform-postgres:5432/platform',
        'REDIS_URL':f'redis://:{redis}@platform-redis:6379/0'}}
    subprocess.run([K,'create','-f','-'],input=json.dumps(obj),text=True,check=True,capture_output=True)
    print(f'{namespace}: isolated credentials created outside Git')
print('Check the generated CI is successful and its GHCR package is public, then review and merge the onboarding PR.')
