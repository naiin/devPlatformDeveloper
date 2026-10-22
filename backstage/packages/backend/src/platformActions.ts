import { createBackendModule } from '@backstage/backend-plugin-api';
import { createTemplateAction } from '@backstage/plugin-scaffolder-node';
import { scaffolderActionsExtensionPoint } from '@backstage/plugin-scaffolder-node';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const schema = { input: { name: (z: any) => z.string().regex(/^[a-z][a-z0-9-]{2,30}$/) } };
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

    );
  } });
} });
