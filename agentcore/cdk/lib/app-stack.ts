import { RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

/**
 * Application infrastructure stack (Foundation Stack pattern) — managed separately
 * from the agentcore-managed AgentCoreStack so that `agentcore deploy` never
 * touches these resources.
 *
 * Deploy: cd agentcore/cdk && npx cdk deploy SlipBox-App-<target>
 * Restore notes after first deploy: aws s3 sync /tmp/slip-box-notes-backup s3://slip-box-notes
 */
export class AppStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Fixed name so agentcore.json KB data source URI stays unchanged.
    // RETAIN so a stack destroy never deletes the note corpus.
    new s3.Bucket(this, 'NotesBucket', {
      bucketName: 'slip-box-notes',
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // All notes — literature-note and permanent-note.
    // PK: note_id (slug-uuid assigned at write time)
    new dynamodb.Table(this, 'ItemsTable', {
      tableName: 'slip-box-items',
      partitionKey: { name: 'note_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // Typed edges between notes.
    // PK: from_id  SK: edge_id (uuid — makes each edge individually addressable)
    // GSI: to_id-index for reverse lookups (what points at this note?)
    const edgesTable = new dynamodb.Table(this, 'EdgesTable', {
      tableName: 'slip-box-edges',
      partitionKey: { name: 'from_id', type: dynamodb.AttributeType.STRING },
      sortKey:      { name: 'edge_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    edgesTable.addGlobalSecondaryIndex({
      indexName: 'to_id-index',
      partitionKey: { name: 'to_id', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });
  }
}
