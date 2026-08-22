import { Duration, Stack, type StackProps } from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
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
        INGEST_SESSIONS_TABLE: 'slip-box-ingest-sessions',
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
    workerFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'IngestSessionsWrite',
        // Only seeds the initial "processing" record and the error-path
        // update — the agent's own hook (app/MyAgent/hooks.py) writes the
        // final complete/skipped-reason status via its own IAM role.
        actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem'],
        resources: ['arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-ingest-sessions'],
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
        SOURCES_TABLE: 'slip-box-sources',
        INGEST_SESSIONS_TABLE: 'slip-box-ingest-sessions',
        UPLOADS_BUCKET: 'slip-box-uploads-690445895420',
        AGENT_RUNTIME_ARN: agentRuntimeArn,
        WORKER_FUNCTION_NAME: workerFn.functionName,
      },
    });
    workerFn.grantInvoke(apiFn);

    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ItemsRead',
        actions: ['dynamodb:GetItem', 'dynamodb:Query', 'dynamodb:Scan'],
        resources: [
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-items',
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-items/index/recent-index',
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-items/index/source-index',
        ],
      })
    );
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'SourcesRead',
        actions: ['dynamodb:GetItem', 'dynamodb:Query'],
        resources: [
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-sources',
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-sources/index/source-key-index',
        ],
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
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'IngestSessionsRead',
        actions: ['dynamodb:GetItem'],
        resources: ['arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-ingest-sessions'],
      })
    );
    apiFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'UploadsPresign',
        // Presigning is a local SigV4 operation with no live AWS call, but
        // S3 still evaluates the *signer's* IAM permissions when the
        // presigned URL is later actually used — the signer needs PutObject
        // even though this Lambda never calls it directly.
        actions: ['s3:PutObject'],
        resources: ['arn:aws:s3:::slip-box-uploads-690445895420/*'],
      })
    );

    // review-todo.md #9 Stage 1 — deterministic S3 -> DynamoDB reconciliation,
    // no agent involved. Triggered by an S3 event notification on
    // NotesBucket (owned by AppStack), so DynamoDB's items table never
    // silently drifts from S3 regardless of write origin (agent tools, a
    // hand-edit, aws s3 sync).
    const reconcilerFn = new lambda.Function(this, 'ReconcilerFunction', {
      functionName: 'slip-box-reconciler',
      runtime: lambda.Runtime.PYTHON_3_14,
      architecture: lambda.Architecture.ARM_64,
      handler: 'reconciler.handler',
      code: codeAsset,
      timeout: Duration.seconds(30),
      memorySize: 512,
      environment: {
        // reconciler.py only reads S3_BUCKET/ITEMS_TABLE/EDGES_TABLE, but it
        // imports linkgen.py, which imports clients.py, which reads every
        // one of these unconditionally at module import time — so all of
        // them have to be set even though this function only uses three.
        S3_BUCKET: 'slip-box-notes',
        ITEMS_TABLE: 'slip-box-items',
        EDGES_TABLE: 'slip-box-edges',
        SOURCES_TABLE: 'slip-box-sources',
        INGEST_SESSIONS_TABLE: 'slip-box-ingest-sessions',
        UPLOADS_BUCKET: 'slip-box-uploads-690445895420',
        AGENT_RUNTIME_ARN: agentRuntimeArn,
      },
    });
    reconcilerFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'NotesReadWrite',
        // PutObject is only exercised by the missing-note_id backfill case
        // (a note created entirely outside the system) — everything else
        // only ever reads.
        actions: ['s3:GetObject', 's3:PutObject'],
        resources: ['arn:aws:s3:::slip-box-notes/*'],
      })
    );
    reconcilerFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ItemsReadWrite',
        actions: ['dynamodb:PutItem', 'dynamodb:GetItem', 'dynamodb:DeleteItem', 'dynamodb:Scan', 'dynamodb:UpdateItem'],
        resources: ['arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-items'],
      })
    );
    reconcilerFn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'EdgesReadDelete',
        actions: ['dynamodb:GetItem', 'dynamodb:Query', 'dynamodb:DeleteItem'],
        resources: [
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-edges',
          'arn:aws:dynamodb:ap-southeast-2:690445895420:table/slip-box-edges/index/to_id-index',
        ],
      })
    );

    // Imported by name rather than a cross-stack construct reference —
    // NotesBucket lives in AppStack, deployed independently on purpose (see
    // both stacks' own top-of-file comments). addEventNotification() on an
    // imported bucket calls s3:PutBucketNotificationConfiguration via a
    // custom resource at deploy time rather than through the bucket's own
    // CloudFormation-owned properties, so this works with no export/import
    // coupling between the two stacks. One real tradeoff: that S3 API call
    // sets the bucket's entire notification config, not an incremental add
    // — safe today since nothing else configures notifications on
    // slip-box-notes, but if anything ever does, whichever deploys last
    // wins.
    const notesBucket = s3.Bucket.fromBucketName(this, 'ImportedNotesBucket', 'slip-box-notes');
    notesBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(reconcilerFn),
      { suffix: '.md' }
    );
    notesBucket.addEventNotification(
      s3.EventType.OBJECT_REMOVED,
      new s3n.LambdaDestination(reconcilerFn),
      { suffix: '.md' }
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
