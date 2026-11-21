import { expect, type APIRequestContext, type Page } from "@playwright/test"

export const E2E_ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME || "admin"
export const E2E_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || "AdminPass123!"

export const E2E_DISPATCHER_USERNAME = process.env.E2E_DISPATCHER_USERNAME || "e2e_dispatcher"
export const E2E_DISPATCHER_PASSWORD =
  process.env.E2E_DISPATCHER_PASSWORD || "DispatcherPass123!"

export const E2E_READER_USERNAME = process.env.E2E_READER_USERNAME || "e2e_reader"
export const E2E_READER_PASSWORD = process.env.E2E_READER_PASSWORD || "ReaderPass123!"

export interface ApiUser {
  id: number
  username: string
  role: "admin" | "dispatcher" | "reader"
  is_active: boolean
}

export function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

export async function apiLogin(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const response = await request.post("/api/v1/auth/login", {
    data: { username, password },
  })
  expect(
    response.ok(),
    `Failed to login as ${username}: HTTP ${response.status()} ${await response.text()}`,
  ).toBeTruthy()
  const body = (await response.json()) as { access_token: string }
  return body.access_token
}

export async function ensureUser(
  request: APIRequestContext,
  adminToken: string,
  user: { username: string; password: string; role: "admin" | "dispatcher" | "reader" },
): Promise<ApiUser> {
  const headers = authHeaders(adminToken)
  const listRes = await request.get("/api/v1/users", { headers })
  expect(listRes.ok(), `Failed to list users: HTTP ${listRes.status()}`).toBeTruthy()
  const users = (await listRes.json()) as ApiUser[]
  const existing = users.find((item) => item.username === user.username)
  if (existing) {
    if (existing.role !== user.role || !existing.is_active) {
      const patchRes = await request.patch(`/api/v1/users/${existing.id}`, {
        headers,
        data: { role: user.role, is_active: true },
      })
      expect(patchRes.ok(), `Failed to update user ${user.username}`).toBeTruthy()
      return (await patchRes.json()) as ApiUser
    }
    return existing
  }

  const createRes = await request.post("/api/v1/users", {
    headers,
    data: user,
  })
  expect(
    createRes.ok(),
    `Failed to create user ${user.username}: HTTP ${createRes.status()}`,
  ).toBeTruthy()
  return (await createRes.json()) as ApiUser
}

export async function loginViaUi(
  page: Page,
  username: string,
  password: string,
  initialPath = "/login",
): Promise<void> {
  await page.goto(initialPath)
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText("Вход в систему", { exact: true })).toBeVisible()
  await page.getByLabel("Логин").fill(username)
  await page.getByLabel("Пароль").fill(password)
  await page.getByRole("button", { name: "Войти", exact: true }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}
