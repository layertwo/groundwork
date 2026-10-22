import {
  CreateAccountCommand,
  GetAccountCommand,
  ListAccountsCommand,
  UpdateAccountCommand,
  type AccountResponse,
  type CreateAccountInput,
  type UpdateAccountInput,
} from '@groundwork/client'
import { client, request } from './sdk'

export function listAccounts(): Promise<AccountResponse[]> {
  return request(() => client.send(new ListAccountsCommand({}))).then(
    (out) => out.accounts ?? [],
  )
}

export function getAccount(id: string): Promise<AccountResponse> {
  return request(() => client.send(new GetAccountCommand({ id })))
}

export function createAccount(data: CreateAccountInput): Promise<AccountResponse> {
  return request(() => client.send(new CreateAccountCommand(data)))
}

export function updateAccount(data: UpdateAccountInput): Promise<AccountResponse> {
  return request(() => client.send(new UpdateAccountCommand(data)))
}
