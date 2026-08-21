import { Duration, Stack, type StackProps } from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';
import * as path from 'path';

/**
 * FastAPI backend infrastructure (Foundation Stack pattern, same as AppStack) —
 * two Lambda functions behind a REST API Gateway.
 *
 * `/ingest` is asynchronous: ApiFunction validates and hands off to
 * WorkerFunction (invoked with InvocationType='Event', not fronted by API
 * Gateway) so the actual invoke_agent_runtime call isn't bound by API
 * Gateway's ~29s Lambda-proxy integration timeout. See docs/build-log.md
 * Week 3 for the full reasoning.
 *
 * Deploy: cd agentcore/cdk && npm run deploy:api (runs app/api/build.sh first)
 */
export class ApiStack extends Stack {
  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);

    // __dirname at runtime is agentcore/cdk/dist/lib/ — four levels up to repo root.
    const codeAsset = lambda.Code.fromAsset(path.join(__dirname, '../../../../app/api/build'));

    const agentRuntimeArn =
      'arn:aws:bedrock-agentcore:ap-southeast-2:690445895420:runtime/SlipBox_MyAgent-wy1BfP93X9';

    // Async ingest worker — no API Gateway in front of it, so no timeout ceiling
    // beyond its own (generous) configured timeout. Only permission it needs is
    // to invoke the agent; the agent's own IAM role handles all S3/DynamoDB writes.
    const workerFn = new lambda.Function(this, 'WorkerFunction', {
      functionName: 'slip-box-api-worker',
      runtime: lambda.Runtime.PYTHON_3_14,
      architecture: lambda.Architecture.ARM_64,
      handler: 'worker.handler',
      code: codeAsset,
      timeout: Duration.seconds(300),
      memorySize: 512,
      environment: {
        AGENT_RUNTIME_ARN: agentRuntimeArn,
      },
    });
    workerFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'InvokeAgent',
        actions: ['bedrock-agentcore:InvokeAgentRuntime'],
        // InvokeAgentRuntime actually operates on the runtime-endpoint
        // sub-resource (.../runtime-endpoint/DEFAULT), not the bare runtime
        // ARN — scoping to just the runtime ARN 403s at call time even though
        // it looks right at a glance. Same pattern as an S3 bucket vs. its
        // objects.
        resources: [agentRuntimeArn, `${agentRuntimeArn}/*`],
      })
    );

    // Request-handling Lambda — FastAPI + Mangum. Never waits on the agent, so
    // stays comfortably inside API Gateway's timeout.
    const apiFn = new lambda.Function(this, 'ApiFunction', {
      functionName: 'slip-box-api',
      runtime: lambda.Runtime.PYTHON_3_14,
      architecture: lambda.Architecture.ARM_64,
      handler: 'main.handler',
      code: codeAsset,
      timeout: Duration.seconds(29),
      memorySize: 512,
      environment: {
        S3_BUCKET: 'slip-box-notes',
        ITEMS_TABLE: 'slip-box-items',
        EDGES_TABLE: 'slip-box-edges',
        AGENT_RUNTIME_ARN: agentRuntimeArn,
        WORKER_FUNCTION_NAME: workerFn.functionName,
      },
    });
    workerFn.grantInvoke(apiFn);

    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ItemsRead',
        actions: ['dynamodb:GetItem', 'dynamodb:Query', 'dynamodb:Scan'],
        resources: ['arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-items'],
      })
    );
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'EdgesReadWrite',
        actions: [
          'dynamodb:GetItem',
          'dynamodb:Query',
          'dynamodb:Scan',
          'dynamodb:UpdateItem',
          'dynamodb:DeleteItem',
        ],
        resources: [
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-edges',
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-edges/index/to_id-index',
        ],
      })
    );
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'NotesFrontmatterRegen',
        actions: ['s3:GetObject', 's3:PutObject'],
        resources: ['arn:aws:s3:::slip-box-notes/*'],
      })
    );

    const api = new apigateway.LambdaRestApi(this, 'Api', {
      handler: apiFn,
      proxy: true,
      apiKeySourceType: apigateway.ApiKeySourceType.HEADER,
      defaultMethodOptions: { apiKeyRequired: true },
      // For the web app's local dev iteration against the live API directly
      // (the deployed app itself goes through a same-origin Next.js Route
      // Handler proxy, so it never hits CORS). CDK's addCorsPreflight()
      // hardcodes apiKeyRequired: false on the generated OPTIONS method
      // regardless of defaultMethodOptions above — no extra config needed
      // for that. Cors.DEFAULT_HEADERS already includes Content-Type and
      // X-Api-Key.
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    const key = api.addApiKey('DemoKey');
    const plan = api.addUsagePlan('DemoUsagePlan', {
      throttle: { rateLimit: 5, burstLimit: 10 },
      quota: { limit: 2000, period: apigateway.Period.DAY },
    });
    plan.addApiKey(key);
    plan.addApiStage({ stage: api.deploymentStage });
  }
}
