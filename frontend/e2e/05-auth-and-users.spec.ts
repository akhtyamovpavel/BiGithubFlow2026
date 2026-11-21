import { expect, test } from "@playwright/test"
import {
  apiLogin,
  authHeaders,
  E2E_ADMIN_PASSWORD,
  E2E_ADMIN_USERNAME,
  E2E_DISPATCHER_PASSWORD,
  E2E_DISPATCHER_USERNAME,
  E2E_READER_PASSWORD,
  E2E_READER_USERNAME,
  ensureUser,
  loginViaUi,
} from "./helpers/auth"

test.describe("Сценарий 5 — Авторизация, роли, истёкшая сессия и управление пользователями", () => {
  test.beforeEach(async ({ request }) => {
    const adminToken = await apiLogin(request, E2E_ADMIN_USERNAME, E2E_ADMIN_PASSWORD)
    await ensureUser(request, adminToken, {
      username: E2E_DISPATCHER_USERNAME,
      password: E2E_DISPATCHER_PASSWORD,
      role: "dispatcher",
    })
    await ensureUser(request, adminToken, {
      username: E2E_READER_USERNAME,
      password: E2E_READER_PASSWORD,
      role: "reader",
    })
  })

  test("защита закрытых разделов, ошибка неверного входа, выход и разграничение прав 403", async ({
    page,
    request,
  }) => {
    // 1. Без сессии закрытые разделы перенаправляют на /login
    await page.goto("/schedule")
    await expect(page).toHaveURL(/\/login$/)
    await page.goto("/users")
    await expect(page).toHaveURL(/\/login$/)

    // 2. Ошибка при неверном пароле (401)
    await page.getByLabel("Логин").fill(E2E_ADMIN_USERNAME)
    await page.getByLabel("Пароль").fill("WrongPassword123!")
    await page.getByRole("button", { name: "Войти", exact: true }).click()
    await expect(page.getByRole("alert")).toContainText("Неверный логин или пароль")

    // 3. Вход читателя: только просмотр и экспорт, 403 на /users
    await loginViaUi(page, E2E_READER_USERNAME, E2E_READER_PASSWORD, "/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Добавить занятие", exact: true })).toHaveCount(0)
    await expect(page.getByRole("link", { name: "Пользователи", exact: true })).toHaveCount(0)

    await page.getByRole("link", { name: "Академические группы", exact: true }).click()
    await expect(
      page.getByRole("heading", { name: "Академические группы", exact: true }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Добавить группу", exact: true })).toHaveCount(0)

    // Прямой переход читателя в административный раздел показывает понятную ошибку 403
    await page.goto("/users")
    await expect(page.getByRole("alert")).toContainText("Ошибка 403")
    await expect(page.getByRole("heading", { name: "Доступ запрещён", exact: true })).toBeVisible()

    // 4. Выход: закрытые разделы снова недоступны
    await page.getByRole("button", { name: "Выйти", exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.goto("/schedule")
    await expect(page).toHaveURL(/\/login$/)
    await page.goto("/groups")
    await expect(page).toHaveURL(/\/login$/)

    // 5. Проверка понятной серверной ошибки 403 при попытке мутации после понижения роли
    const adminToken = await apiLogin(request, E2E_ADMIN_USERNAME, E2E_ADMIN_PASSWORD)
    const downgradeUsername = `e2e_downgrade_${Date.now()}`
    const downgradePassword = "DowngradePass123!"
    const createdUser = await ensureUser(request, adminToken, {
      username: downgradeUsername,
      password: downgradePassword,
      role: "dispatcher",
    })

    await loginViaUi(page, downgradeUsername, downgradePassword, "/groups")
    await expect(page.getByRole("button", { name: "Добавить группу", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Добавить группу", exact: true }).click()

    const dialog = page.getByRole("dialog")
    await dialog.getByLabel("Шифр группы").fill("Б05-403")
    await dialog.getByLabel("Факультет").fill("ФПМИ")
    await dialog.getByLabel("Курс").fill("2")
    await dialog.getByLabel("Количество студентов").fill("20")

    // Понижаем роль аккаунта до reader на сервере — права меняются немедленно
    const downgradeRes = await request.patch(`/api/v1/users/${createdUser.id}`, {
      headers: authHeaders(adminToken),
      data: { role: "reader" },
    })
    expect(downgradeRes.ok()).toBeTruthy()

    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
    await expect(dialog.getByRole("alert")).toContainText(
      "Недостаточно прав для выполнения этого действия.",
    )
  })

  test("администратор создаёт пользователя, меняет роль и блокирует аккаунт", async ({ page }) => {
    const managedUsername = `e2e_user_${Date.now()}`
    const managedPassword = "ManagedUser123!"

    await loginViaUi(page, E2E_ADMIN_USERNAME, E2E_ADMIN_PASSWORD, "/schedule")
    await page.getByRole("link", { name: "Пользователи", exact: true }).click()
    await expect(page).toHaveURL(/\/users$/)
    await expect(page.getByRole("heading", { name: "Пользователи", exact: true })).toBeVisible()

    // 1. Создание пользователя с ролью Читатель
    await page.getByRole("button", { name: "Создать пользователя", exact: true }).click()
    const createDialog = page.getByRole("dialog")
    await expect(createDialog).toBeVisible()
    await createDialog.getByLabel("Логин *", { exact: true }).fill(managedUsername)
    await createDialog.getByLabel("Пароль *", { exact: true }).fill(managedPassword)
    await createDialog.getByLabel("Роль *", { exact: true }).selectOption("reader")
    await createDialog.getByRole("button", { name: "Создать", exact: true }).click()
    await expect(createDialog).toHaveCount(0)

    const userRow = page.getByRole("row").filter({ hasText: managedUsername })
    await expect(userRow).toBeVisible()
    await expect(userRow).toContainText("Активен")

    // 2. Смена роли на Диспетчер и проверка сохранения после перезагрузки
    const roleSelect = userRow.getByLabel(`Роль пользователя ${managedUsername}`)
    await roleSelect.selectOption("dispatcher")
    await expect(roleSelect).toHaveValue("dispatcher")
    await page.reload()
    const reloadedRow = page.getByRole("row").filter({ hasText: managedUsername })
    await expect(reloadedRow.getByLabel(`Роль пользователя ${managedUsername}`)).toHaveValue(
      "dispatcher",
    )

    // 3. Блокировка аккаунта через подтверждение
    await reloadedRow.getByRole("button", { name: `Заблокировать ${managedUsername}` }).click()
    const confirmDialog = page.getByRole("alertdialog")
    await expect(confirmDialog).toBeVisible()
    await confirmDialog.getByRole("button", { name: "Заблокировать", exact: true }).click()
    await expect(confirmDialog).toHaveCount(0)
    await expect(reloadedRow).toContainText("Заблокирован")

    // 4. Выход администратора и проверка, что заблокированный аккаунт не может войти
    await page.getByRole("button", { name: "Выйти", exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.getByLabel("Логин").fill(managedUsername)
    await page.getByLabel("Пароль").fill(managedPassword)
    await page.getByRole("button", { name: "Войти", exact: true }).click()
    await expect(page.getByRole("alert")).toContainText("аккаунт заблокирован")

    // 5. Разблокировка аккаунта администратором и успешный вход
    await loginViaUi(page, E2E_ADMIN_USERNAME, E2E_ADMIN_PASSWORD, "/users")
    const blockedRow = page.getByRole("row").filter({ hasText: managedUsername })
    await blockedRow.getByRole("button", { name: `Разблокировать ${managedUsername}` }).click()
    await expect(blockedRow).toContainText("Активен")
  })

  test("истёкшая или отозванная сессия (401) переводит на экран входа с понятным уведомлением", async ({
    page,
    request,
  }) => {
    await loginViaUi(page, E2E_DISPATCHER_USERNAME, E2E_DISPATCHER_PASSWORD, "/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()

    // Отзываем текущую сессию на реальном API, имитируя истечение/отзыв токена
    const token = await page.evaluate(() =>
      window.localStorage.getItem("schedule_service_access_token"),
    )
    expect(token).toBeTruthy()
    const revokeRes = await request.post("/api/v1/auth/logout", {
      headers: authHeaders(token!),
    })
    expect(revokeRes.status()).toBe(204)

    // Следующее действие пользователя получает 401 и переводит на /login с баннером об истёкшей сессии
    await page.getByRole("button", { name: "Обновить", exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole("alert")).toContainText("Сессия истекла или была отозвана")

    // Повторный вход с экрана истёкшей сессии возвращает пользователя в расписание
    await page.getByLabel("Логин").fill(E2E_DISPATCHER_USERNAME)
    await page.getByLabel("Пароль").fill(E2E_DISPATCHER_PASSWORD)
    await page.getByRole("button", { name: "Войти", exact: true }).click()
    await expect(page).toHaveURL(/\/schedule$/)
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()
  })
})
