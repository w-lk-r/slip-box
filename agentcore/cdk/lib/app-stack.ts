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
    // GSI: recent-index for the Recent list, sorted by created_at. A plain
    // Scan (the original design) has no ordering guarantee at all — once the
    // corpus outgrew one page, "recent" silently stopped being recent. gsi_pk
    // is a constant ("item") written on every item so a single Query can
    // return the whole table sorted by created_at, since GSI Query needs an
    // exact partition-key match, not a real per-item value to partition on.
    const itemsTable = new dynamodb.Table(this, 'ItemsTable', {
      tableName: 'slip-box-items',
      partitionKey: { name: 'note_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    itemsTable.addGlobalSecondaryIndex({
      indexName: 'recent-index',
      partitionKey: { name: 'gsi_pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'created_at', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // GSI: source-index — "every note from this source" reverse lookup,
    // keyed on the source_id each item cites (see SourcesTable below).
    itemsTable.addGlobalSecondaryIndex({
      indexName: 'source-index',
      partitionKey: { name: 'source_id', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // Structured source citations — replaces the old flat source_url string.
    // PK: source_id. GSI: source-key-index for write-time dedup (normalized
    // URL today; a content-hash for PDF sources once that ships) so the same
    // source cited by multiple notes resolves to one shared record instead
    // of a fresh duplicate every time.
    const sourcesTable = new dynamodb.Table(this, 'SourcesTable', {
      tableName: 'slip-box-sources',
      partitionKey: { name: 'source_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    sourcesTable.addGlobalSecondaryIndex({
      indexName: 'source-key-index',
      partitionKey: { name: 'source_key', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
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
