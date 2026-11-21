import { expect, test, type APIRequestContext } from "@playwright/test"
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

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + days))
  return dt.toISOString().slice(0, 10)
}

async function pickCleanOddMonday(request: APIRequestContext, token: string): Promise<string> {
  const headers = authHeaders(token)
  const groupsRes = await request.get("/api/v1/groups/?limit=100", { headers })
  const groups = (await groupsRes.json()) as Array<{ id: number; name: string }>
  const group = groups.find((g) => g.name === "Б05-401")
  if (!group) return "2026-10-19"
  const schedRes = await request.get(`/api/v1/schedule/group/${group.id}`, { headers })
  const sched = (await schedRes.json()) as {
    days: Array<{ lessons: Array<{ exceptions?: Array<{ occurrence_date: string }> }> }>
  }
  const usedDates = new Set<string>()
  for (const day of sched.days) {
    for (const lesson of day.lessons) {
      for (const exc of lesson.exceptions || []) usedDates.add(exc.occurrence_date)
    }
  }
  let candidate = "2026-10-19"
  while (usedDates.has(candidate) || usedDates.has(addDays(candidate, 14))) {
    candidate = addDays(candidate, 28)
  }
  return candidate
}

test.describe("Сценарий 6 — Перенос и отмена занятия на выбранную дату", () => {
  let targetMonday = "2026-10-19"

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
    targetMonday = await pickCleanOddMonday(request, adminToken)
  })

  test("диспетчер переносит и отменяет занятие на дату, остальные недели без изменений, 409 и защита от дубля", async ({
    page,
  }) => {
    const targetThursday = addDays(targetMonday, 3)
    const nextMonday = addDays(targetMonday, 7)
    const conflictMonday = addDays(targetMonday, 14)
    const freeThursday = addDays(conflictMonday, 3)

    await loginViaUi(page, E2E_DISPATCHER_USERNAME, E2E_DISPATCHER_PASSWORD, "/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()

    // Выбираем группу Б05-401 и конкретную календарную неделю
    await page.getByRole("combobox", { name: "Академическая группа", exact: true }).click()
    await page.getByRole("option", { name: "Б05-401", exact: true }).click()
    await page.getByLabel("Дата учебной недели").fill(targetMonday)

    const table = page.getByRole("table", { name: "Расписание по дням и парам" })
    await expect(
      table.getByRole("heading", { name: "Математический анализ", exact: true }),
    ).toBeVisible()

    // 1. Успешный перенос одного вхождения (Понедельник -> Четверг, 4 пара, Главный корпус 202)
    await page
      .getByRole("button", { name: "Перенести Математический анализ (Б05-401)", exact: true })
      .click()
    const moveDialog = page.getByRole("dialog")
    await expect(moveDialog).toBeVisible()
    await expect(moveDialog.getByRole("status")).toContainText("Область: одно занятие")

    await moveDialog.getByLabel("Новая дата *").fill(targetThursday)
    await moveDialog
      .getByLabel("Новый временной слот *")
      .selectOption({ label: "Четверг · 4 пара (13:55–15:20)" })
    await moveDialog
      .getByLabel("Новая аудитория *")
      .selectOption({ label: "Главный корпус · 202 (120 мест)" })
    await moveDialog.getByLabel("Причина изменения *").fill("Конференция в аудитории 115")

    await moveDialog.getByRole("button", { name: "Продолжить", exact: true }).click()
    await expect(moveDialog).toContainText("Подтверди операцию")
    await expect(moveDialog).toContainText("Конференция в аудитории 115")
    await moveDialog.getByRole("button", { name: "Подтвердить перенос", exact: true }).click()
    await expect(moveDialog).toHaveCount(0)

    // На выбранной неделе занятие перенесено на четверг (13:55–15:20), а на понедельнике отмечено как перенесённое
    await expect(table.getByText("Перенесено: Математический анализ (Б05-401)")).toBeVisible()
    await expect(table.getByText(targetThursday)).toBeVisible()
    await expect(table.getByText("13:55–15:20")).toBeVisible()

    // 2. Успешная отмена одного вхождения (Алгоритмы и структуры данных на выбранный понедельник)
    await page
      .getByRole("button", { name: "Отменить Алгоритмы и структуры данных (Б05-401)", exact: true })
      .click()
    const cancelDialog = page.getByRole("dialog")
    await expect(cancelDialog).toBeVisible()
    await cancelDialog.getByLabel("Причина изменения *").fill("Плановые работы в лаборатории")
    await cancelDialog.getByRole("button", { name: "Продолжить", exact: true }).click()
    await expect(cancelDialog).toContainText("Подтверди операцию")
    await cancelDialog.getByRole("button", { name: "Подтвердить отмену", exact: true }).click()
    await expect(cancelDialog).toHaveCount(0)

    await expect(
      table.getByRole("heading", { name: "Алгоритмы и структуры данных", exact: true }),
    ).toHaveCount(0)
    await expect(
      table.getByText("Отменено: Алгоритмы и структуры данных (Б05-401)"),
    ).toBeVisible()

    // 3. Проверка, что следующая неделя осталась без изменений
    await page.getByRole("button", { name: "Следующая неделя", exact: true }).click()
    await expect(page.getByLabel("Дата учебной недели")).toHaveValue(nextMonday)
    await expect(
      table.getByRole("heading", { name: "Математический анализ", exact: true }),
    ).toBeVisible()
    await expect(
      table.getByRole("heading", { name: "Алгоритмы и структуры данных", exact: true }),
    ).toBeVisible()
    await expect(table.getByText(targetThursday)).toHaveCount(0)

    // 4. Конфликт 409: перенос в занятый группой слот показывает причину и сохраняет введённые данные
    await page.getByLabel("Дата учебной недели").fill(conflictMonday)
    await page
      .getByRole("button", { name: "Перенести Математический анализ (Б05-401)", exact: true })
      .click()
    const conflictDialog = page.getByRole("dialog")
    await conflictDialog.getByLabel("Новая дата *").fill(conflictMonday)
    await conflictDialog
      .getByLabel("Новый временной слот *")
      .selectOption({ label: "Понедельник · 2 пара (10:45–12:10)" })
    await conflictDialog.getByLabel("Причина изменения *").fill("Проверка коллизии 409")
    await conflictDialog.getByRole("button", { name: "Продолжить", exact: true }).click()
    await conflictDialog.getByRole("button", { name: "Подтвердить перенос", exact: true }).click()

    await expect(conflictDialog.getByRole("alert")).toContainText("Обнаружена коллизия расписания")
    await expect(conflictDialog.getByRole("alert")).toContainText("Учебная группа уже занята")
    await expect(conflictDialog.getByLabel("Причина изменения *")).toHaveValue(
      "Проверка коллизии 409",
    )
    await expect(conflictDialog.getByLabel("Новая дата *")).toHaveValue(conflictMonday)

    // 5. Исправляем слот и проверяем, что повторный клик не отправляет дублирующий POST
    let exceptionPostCount = 0
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/exceptions")) {
        exceptionPostCount += 1
      }
    })
    await conflictDialog.getByLabel("Новая дата *").fill(freeThursday)
    await conflictDialog
      .getByLabel("Новый временной слот *")
      .selectOption({ label: "Четверг · 5 пара (15:30–16:55)" })
    await conflictDialog.getByRole("button", { name: "Продолжить", exact: true }).click()
    const confirmBtn = conflictDialog.getByRole("button", {
      name: "Подтвердить перенос",
      exact: true,
    })
    await confirmBtn.evaluate((el) => {
      ;(el as HTMLButtonElement).click()
      ;(el as HTMLButtonElement).click()
    })
    await expect(conflictDialog).toHaveCount(0)
    expect(exceptionPostCount).toBe(1)
  })

  test("читатель не видит действия переноса и отмены в сетке расписания", async ({ page }) => {
    await loginViaUi(page, E2E_READER_USERNAME, E2E_READER_PASSWORD, "/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()
    await page.getByLabel("Дата учебной недели").fill(targetMonday)
    await expect(page.getByRole("button", { name: /^Перенести / })).toHaveCount(0)
    await expect(page.getByRole("button", { name: /^Отменить / })).toHaveCount(0)
  })
})
