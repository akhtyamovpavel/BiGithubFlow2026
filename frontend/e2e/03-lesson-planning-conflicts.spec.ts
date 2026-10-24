import { expect, test, type APIRequestContext } from "@playwright/test"

const TARGET_SLOT_LABEL = "Понедельник · 5 пара (15:30–16:55)"

async function cleanupMondaySlotFiveLessons(request: APIRequestContext) {
  const response = await request.get("/api/v1/lessons/?limit=500")
  if (!response.ok()) {
    return
  }
  const lessons = (await response.json()) as Array<{
    id: number
    time_slot: { day_of_week: number; slot_number: number } | null
  }>
  for (const lesson of lessons) {
    if (lesson.time_slot?.day_of_week === 1 && lesson.time_slot.slot_number === 5) {
      await request.delete(`/api/v1/lessons/${lesson.id}`)
    }
  }
}

test.describe("Сценарий 3 — Планирование занятия и защита от коллизий (409 Conflict)", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupMondaySlotFiveLessons(request)
  })

  test.afterEach(async ({ request }) => {
    await cleanupMondaySlotFiveLessons(request)
  })

  test("успешное добавление занятия в свободный слот и отображение ошибки 409 при накладке", async ({
    page,
  }) => {
    await page.goto("/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()
    await expect(page.getByText("Занятий в сетке:")).toContainText("20")

    // 1. Успешное добавление нового занятия в свободный слот (Понедельник, 5 пара)
    await page.getByRole("button", { name: "Добавить занятие", exact: true }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()

    await dialog
      .getByLabel("Дисциплина")
      .selectOption({ label: "Процесс разработки и DevOps" })
    await dialog.getByLabel("Учебная группа").selectOption({ label: "Б05-401" })
    await dialog.getByLabel("Преподаватель").selectOption({ label: "Иванов Сергей Петрович" })
    await dialog
      .getByLabel("Аудитория")
      .selectOption({ label: "Главный корпус · 115 (150 мест)" })
    await dialog.getByLabel("Временной слот").selectOption({ label: TARGET_SLOT_LABEL })
    await dialog.getByLabel("Тип занятия").selectOption({ label: "Семинар" })
    await dialog.getByLabel("Чётность недели").selectOption({ label: "Каждую неделю" })

    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
    await expect(dialog).toHaveCount(0)

    await expect(page.getByText("Занятий в сетке:")).toContainText("21")
    await expect(page.getByText("15:30–16:55").first()).toBeVisible()

    // 2. Попытка поставить вторую пару тому же преподавателю/группе и в ту же аудиторию в тот же слот
    await page.getByRole("button", { name: "Добавить занятие", exact: true }).click()
    const conflictDialog = page.getByRole("dialog")
    await expect(conflictDialog).toBeVisible()

    await conflictDialog
      .getByLabel("Дисциплина")
      .selectOption({ label: "Математический анализ" })
    await conflictDialog.getByLabel("Учебная группа").selectOption({ label: "Б05-401" })
    await conflictDialog
      .getByLabel("Преподаватель")
      .selectOption({ label: "Иванов Сергей Петрович" })
    await conflictDialog
      .getByLabel("Аудитория")
      .selectOption({ label: "Главный корпус · 115 (150 мест)" })
    await conflictDialog.getByLabel("Временной слот").selectOption({ label: TARGET_SLOT_LABEL })

    await conflictDialog.getByRole("button", { name: "Сохранить", exact: true }).click()

    const alert = conflictDialog.getByRole("alert")
    await expect(alert).toBeVisible()
    await expect(alert).toContainText("Обнаружена коллизия расписания")
    await expect(alert).toContainText("Преподаватель уже занят")
  })
})
