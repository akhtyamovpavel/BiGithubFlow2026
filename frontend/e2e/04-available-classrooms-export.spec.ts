import fs from "node:fs"
import { expect, test } from "@playwright/test"
import {
  apiLogin,
  E2E_ADMIN_PASSWORD,
  E2E_ADMIN_USERNAME,
  E2E_READER_PASSWORD,
  E2E_READER_USERNAME,
  ensureUser,
  loginViaUi,
} from "./helpers/auth"

test.describe("Сценарий 4 — Поиск свободных аудиторий и экспорт", () => {
  test.beforeEach(async ({ request }) => {
    const adminToken = await apiLogin(request, E2E_ADMIN_USERNAME, E2E_ADMIN_PASSWORD)
    await ensureUser(request, adminToken, {
      username: E2E_READER_USERNAME,
      password: E2E_READER_PASSWORD,
      role: "reader",
    })
  })

  test("читатель ищет свободные аудитории и экспортирует расписание в .ics и .csv без прав редактирования", async ({
    page,
  }) => {
    await loginViaUi(page, E2E_READER_USERNAME, E2E_READER_PASSWORD, "/schedule")
    await expect(
      page.getByRole("heading", { name: "Сетка расписания", exact: true }),
    ).toBeVisible()

    // Читатель не видит кнопку добавления занятия
    await expect(page.getByRole("button", { name: "Добавить занятие", exact: true })).toHaveCount(0)

    // 1. Поиск свободных аудиторий на Понедельник · 1 пара (где Главный корпус · 115 занята) с вместимостью >= 50
    const searchSection = page.getByRole("region", {
      name: "Поиск свободных аудиторий",
      exact: true,
    })
    await expect(searchSection).toBeVisible()

    await searchSection
      .getByLabel("Слот для поиска аудитории")
      .selectOption({ label: "Понедельник · 1 пара (09:00–10:25)" })
    await searchSection.getByLabel("Минимальная вместимость").fill("50")
    await searchSection
      .getByRole("button", { name: "Найти свободные аудитории", exact: true })
      .click()

    // Свободные аудитории вместимостью >= 50 на этот слот: Главный корпус · 202 (120) и Цифра · 101 (80)
    await expect(searchSection.getByText("Главный корпус · 202", { exact: true })).toBeVisible()
    await expect(searchSection.getByText("Цифра · 101", { exact: true })).toBeVisible()
    // Занятая на 1-й паре понедельника аудитория Главный корпус · 115 (150 мест) и малая КПМ · 505 (30 мест) не должны отображаться
    await expect(searchSection.getByText("Главный корпус · 115", { exact: true })).toHaveCount(0)
    await expect(searchSection.getByText("КПМ · 505", { exact: true })).toHaveCount(0)

    // 2. Проверка скачивания расписания в форматах .ics и .csv с авторизацией
    await page.getByRole("combobox", { name: "Академическая группа", exact: true }).click()
    await page.getByRole("option", { name: "Б05-401", exact: true }).click()

    const icsDownloadPromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Скачать .ics", exact: true }).click()
    const icsDownload = await icsDownloadPromise
    expect(icsDownload.suggestedFilename()).toMatch(/^schedule_group_\d+\.ics$/)
    const icsPath = await icsDownload.path()
    expect(icsPath).toBeTruthy()
    expect(fs.readFileSync(icsPath!, "utf-8")).toContain("BEGIN:VCALENDAR")

    const csvDownloadPromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Скачать .csv", exact: true }).click()
    const csvDownload = await csvDownloadPromise
    expect(csvDownload.suggestedFilename()).toMatch(/^schedule_group_\d+\.csv$/)
    const csvPath = await csvDownload.path()
    expect(csvPath).toBeTruthy()
    expect(fs.readFileSync(csvPath!, "utf-8")).toContain("Предмет")
  })
})
