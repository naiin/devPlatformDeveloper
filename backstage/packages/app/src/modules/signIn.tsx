import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { SignInPageBlueprint } from '@backstage/plugin-app-react';
import { githubAuthApiRef } from '@backstage/core-plugin-api';
import { SignInPage } from '@backstage/core-components';
export const signInModule = createFrontendModule({
  pluginId: 'app',
  extensions: [SignInPageBlueprint.make({ params: {
    loader: async () => props => <SignInPage {...props} providers={[
      { id: 'github-auth-provider', title: 'GitHub', message: 'Sign in as the platform owner to create services', apiRef: githubAuthApiRef },
      'guest',
    ]} />,
  } })],
});
