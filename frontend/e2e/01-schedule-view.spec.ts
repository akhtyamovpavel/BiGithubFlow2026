import { expect, test, type Page } from "@playwright/test"

async function selectFilterOption(page: Page, label: string, option: string) {
  await page.getByRole("combobox", { name: label, exact: true }).click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test.describe("Сценарий 1 — Просмотр расписания", () => {
  test("открытие главной страницы, фильтрация по группе, преподавателю и чётности недель", async ({
    page,
  }) => {
    await page.goto("/")
    await expect(page).toHaveURL(/\/schedule$/)
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()

    const scheduleTable = page.getByRole("table", { name: "Расписание по дням и парам" })
    await expect(scheduleTable).toBeVisible()

    for (const day of ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]) {
      await expect(scheduleTable.getByRole("columnheader", { name: day, exact: true })).toBeVisible()
    }

    await expect(page.getByText("Занятий в сетке:")).toContainText("20")

    // Выбор учебной группы Б01-202, у которой во вторник на 2-й паре чередуются нечётная и чётная недели
    await selectFilterOption(page, "Академическая группа", "Б01-202")
    await expect(page.getByText("Занятий в сетке:")).toContainText("4")
    await expect(
      scheduleTable.getByRole("heading", { name: "Машинное обучение", exact: true }),
    ).toBeVisible()
    await expect(
      scheduleTable.getByRole("heading", { name: "Процесс разработки и DevOps", exact: true }),
    ).toBeVisible()
    await expect(
      scheduleTable.getByRole("heading", { name: "Базы данных и SQL", exact: true }),
    ).toBeVisible()

    // Переключение фильтра чётности недель: Нечётная неделя
    await page.getByRole("tab", { name: "Нечётная", exact: true }).click()
    await expect(page.getByText("Занятий в сетке:")).toContainText("3")
    await expect(
      scheduleTable.getByRole("heading", { name: "Процесс разработки и DevOps", exact: true }),
    ).toBeVisible()
    await expect(
      scheduleTable.getByRole("heading", { name: "Базы данных и SQL", exact: true }),
    ).toHaveCount(0)

    // Переключение фильтра чётности недель: Чётная неделя
    await page.getByRole("tab", { name: "Чётная", exact: true }).click()
    await expect(page.getByText("Занятий в сетке:")).toContainText("3")
    await expect(
      scheduleTable.getByRole("heading", { name: "Базы данных и SQL", exact: true }),
    ).toBeVisible()
    await expect(
      scheduleTable.getByRole("heading", { name: "Процесс разработки и DevOps", exact: true }),
    ).toHaveCount(0)

    // Возврат ко всем неделям и фильтрация по преподавателю
    await page.getByRole("tab", { name: "Все недели", exact: true }).click()
    await selectFilterOption(page, "Академическая группа", "Все")
    await selectFilterOption(page, "Преподаватель", "Иванов Сергей Петрович")
    await expect(page.getByText("Занятий в сетке:")).toContainText("2")
    await expect(
      scheduleTable.getByRole("heading", { name: "Математический анализ", exact: true }),
    ).toBeVisible()
    await expect(
      scheduleTable.getByRole("heading", { name: "Линейная алгебра и геометрия", exact: true }),
    ).toBeVisible()
  })
})
