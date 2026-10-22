import { createBackendModule } from '@backstage/backend-plugin-api';
import { createTemplateAction } from '@backstage/plugin-scaffolder-node';
import { scaffolderActionsExtensionPoint } from '@backstage/plugin-scaffolder-node';
import { readFile, writeFile } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { request } from 'node:https';
import { join } from 'node:path';
const schema = { input: { name: (z: any) => z.string().regex(/^[a-z][a-z0-9-]{2,30}$/) } };
async function post(path: string, body: unknown) {
  const root = '/var/run/secrets/kubernetes.io/serviceaccount';
  const [token, ca] = await Promise.all([readFile(join(root, 'token'), 'utf8'), readFile(join(root, 'ca.crt'))]);
  return new Promise<void>((resolve, reject) => {
    const req = request({ hostname: process.env.KUBERNETES_SERVICE_HOST, port: 443, path,
      method: 'POST', ca, headers: { Authorization: `Bearer ${token.trim()}`, 'Content-Type': 'application/json' } }, res => {
      res.resume(); res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) resolve();
        else reject(new Error(`Credential provisioning returned HTTP ${res.statusCode}; existing namespaces are never adopted or overwritten`));
      });
    });
    req.on('error', reject); req.end(JSON.stringify(body));
  });
}
export default createBackendModule({ pluginId: 'scaffolder', moduleId: 'platform-actions', register(reg) {
  reg.registerInit({ deps: { actions: scaffolderActionsExtensionPoint }, async init({ actions }) {
    actions.addActions(
      createTemplateAction({ id: 'platform:configure', description: 'Personalize the tested service release pipeline', schema,
        async handler(ctx) {
          const name = ctx.input.name;
          const files = ['.github/workflows/ci.yml', 'scripts/release.py'];
          for (const file of files) {
            const path = join(ctx.workspacePath, file);
            let text = await readFile(path, 'utf8');
            text = text.replaceAll('ghcr.io/naiin/devplatformdeveloper-api', `ghcr.io/naiin/${name}`)
              .replaceAll('naiin/devPlatformDeveloper', `naiin/${name}`);
            await writeFile(path, text);
          }
          const valuesPath = join(ctx.workspacePath, 'gitops/environments/staging/platform/values.yaml');
          const { mkdir } = await import('node:fs/promises');
          await mkdir(join(ctx.workspacePath, 'gitops/environments/staging/platform'), { recursive: true });
          await writeFile(valuesPath, `environment: staging
image:
  repository: ghcr.io/naiin/${name}
  tag: pending
  digest: ''
ingress:
  host: demo.talos.test
  path: /services/${name}
`);
        } }),
      createTemplateAction({ id: 'platform:credentials', description: 'Create a new isolated namespace and random database credentials; never log or commit credentials', schema,
        async handler(ctx) {
          const namespace = `staging-${ctx.input.name}`;
          await post('/api/v1/namespaces', { apiVersion: 'v1', kind: 'Namespace', metadata: { name: namespace,
            labels: { 'pod-security.kubernetes.io/enforce': 'restricted', 'devplatform.io/managed-by': 'backstage' } } });
          const postgres = randomBytes(24).toString('hex'), redis = randomBytes(24).toString('hex');
          await post(`/api/v1/namespaces/${namespace}/secrets`, { apiVersion: 'v1', kind: 'Secret',
            metadata: { name: 'platform-credentials', namespace }, type: 'Opaque', stringData: {
              POSTGRES_PASSWORD: postgres, REDIS_PASSWORD: redis,
              DATABASE_URL: `postgresql+psycopg://platform:${postgres}@platform-postgres:5432/platform`,
              REDIS_URL: `redis://:${redis}@platform-redis:6379/0`,
            } });
          ctx.logger.info(`Provisioned credentials in ${namespace}; no credentials were included in Git or task outputs`);
        } }),
    );
  } });
} });
