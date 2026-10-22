import { GroundworkClient } from '@groundwork/client'
import { ApiError } from './client'

// Generated Smithy client. Requests are same-origin (Vite proxies /api in dev,
// FastAPI serves the built SPA in production), so the session cookie is sent
// automatically.
const client = new GroundworkClient({ endpoint: window.location.origin })

// The API rejects mutating requests without this header (CSRF protection).
client.middlewareStack.add(
  (next) => async (args) => {
    const request = args.request as { method?: string; headers: Record<string, string> }
    const method = (request.method ?? 'GET').toUpperCase()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      request.headers['x-requested-with'] = 'XMLHttpRequest'
    }
    return next(args)
  },
  { step: 'build', name: 'csrfHeader' },
)

/**
 * Send a generated command, normalizing errors to {@link ApiError} so existing
 * UI code keeps reading `err.detail`.
 */
export async function request<T>(send: () => Promise<T>): Promise<T> {
  try {
    return await send()
  } catch (error) {
    const err = error as {
      detail?: string
      message?: string
      $metadata?: { httpStatusCode?: number }
    }
    throw new ApiError(
      err.$metadata?.httpStatusCode ?? 500,
      err.detail ?? err.message ?? 'Request failed',
    )
  }
}

export { client }
