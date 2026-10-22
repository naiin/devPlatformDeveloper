import { createBackendModule } from '@backstage/backend-plugin-api';
import { AuthorizeResult, isReadPermission } from '@backstage/plugin-permission-common';
import { PolicyDecision } from '@backstage/plugin-permission-common';
import { PermissionPolicy, PolicyQuery, PolicyQueryUser } from '@backstage/plugin-permission-node';
import { policyExtensionPoint } from '@backstage/plugin-permission-node/alpha';
class PlatformPolicy implements PermissionPolicy {
  async handle(request: PolicyQuery, user?: PolicyQueryUser): Promise<PolicyDecision> {
    const owner = user?.info.userEntityRef === 'user:default/naiin';
    return { result: owner || isReadPermission(request.permission) ? AuthorizeResult.ALLOW : AuthorizeResult.DENY };
  }
}
export default createBackendModule({
  pluginId: 'permission', moduleId: 'platform-policy',
  register(reg) {
    reg.registerInit({ deps: { policy: policyExtensionPoint }, async init({ policy }) {
      policy.setPolicy(new PlatformPolicy());
    } });
  },
});
