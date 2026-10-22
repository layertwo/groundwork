import {
  ListAuditEntriesCommand,
  type ListAuditEntriesCommandInput,
  type ListAuditEntriesCommandOutput,
} from '@groundwork/client'
import { client, request } from './sdk'

export function listAuditLogs(
  filters: ListAuditEntriesCommandInput,
): Promise<ListAuditEntriesCommandOutput> {
  return request(() => client.send(new ListAuditEntriesCommand(filters)))
}
