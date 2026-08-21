import { CfnOutput, Stack, type StackProps } from 'aws-cdk-lib';
import * as amplify from 'aws-cdk-lib/aws-amplify';
import { Construct } from 'constructs';

export interface AmplifyStackProps extends StackProps {
  /** GitHub PAT authorizing the Amplify GitHub App connection. Not stored by CloudFormation
   * beyond initial connection setup — see app/web/README.md for how to generate one. */
  githubToken: string;
  /** Same value used by the mobile app / local .env.local — the API Gateway DemoKey. */
  apiKey: string;
  /** HTTP Basic Auth password gating the whole site — nothing else protects the pages
   * themselves (the API_KEY only protects the AWS backend from direct calls). Generated
   * fresh per deploy if not supplied; see the CfnOutput for retrieving it. */
  basicAuthPassword: string;
}

const REPOSITORY = 'https://github.com/w-lk-r/slip-box';
const BACKEND_BASE_URL = 'https://q8gysyecd0.execute-api.ap-southeast-2.amazonaws.com/prod';
const BASIC_AUTH_USERNAME = 'slipbox';

// Monorepo build spec — app/web is a subdirectory, not the repo root.
const BUILD_SPEC = `
version: 1
applications:
  - appRoot: app/web
    frontend:
      phases:
        preBuild:
          commands:
            - npm ci
        build:
          commands:
            - npm run build
      artifacts:
        baseDirectory: .next
        files:
          - '**/*'
      cache:
        paths:
          - node_modules/**/*
`;

export class AmplifyStack extends Stack {
  constructor(scope: Construct, id: string, props: AmplifyStackProps) {
    super(scope, id, props);

    const basicAuthConfig: amplify.CfnApp.BasicAuthConfigProperty = {
      enableBasicAuth: true,
      username: BASIC_AUTH_USERNAME,
      password: props.basicAuthPassword,
    };

    const app = new amplify.CfnApp(this, 'App', {
      name: 'slip-box-web',
      repository: REPOSITORY,
      accessToken: props.githubToken,
      platform: 'WEB_COMPUTE', // Next.js SSR/Route Handlers, not a static-only site
      buildSpec: BUILD_SPEC,
      basicAuthConfig,
      environmentVariables: [
        { name: 'API_KEY', value: props.apiKey },
        { name: 'BACKEND_BASE_URL', value: BACKEND_BASE_URL },
        // Amplify's own monorepo detection also needs this for the console UI;
        // the buildSpec's appRoot above is what actually drives the build.
        { name: 'AMPLIFY_MONOREPO_APP_ROOT', value: 'app/web' },
      ],
    });

    const branch = new amplify.CfnBranch(this, 'MainBranch', {
      appId: app.attrAppId,
      branchName: 'main',
      enableAutoBuild: true,
      stage: 'PRODUCTION',
    });

    // Basic auth password isn't echoed here — it's whatever you passed in via
    // AMPLIFY_BASIC_AUTH_PASSWORD, so you already have it. Username is fixed
    // and safe to print.
    new CfnOutput(this, 'AppId', { value: app.attrAppId });
    new CfnOutput(this, 'DefaultDomain', {
      value: `https://${branch.branchName}.${app.attrDefaultDomain}`,
    });
    new CfnOutput(this, 'BasicAuthUsername', { value: BASIC_AUTH_USERNAME });
  }
}
