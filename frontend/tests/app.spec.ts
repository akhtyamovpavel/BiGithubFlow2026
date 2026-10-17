import { expect, test, type Page } from "@playwright/test"
import { demoLessons } from "../src/lib/demo-schedule"
import type { Group, Teacher } from "../src/lib/models"

const metadata = { created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" }
const initialGroup: Group = {
  ...metadata,
  id: 1,
  name: "Б05-201",
  faculty: "БИ",
  course_number: 2,
  student_count: 25,
  is_active: true,
}
const initialTeacher: Teacher = {
  ...metadata,
  id: 1,
  full_name: "Смирнова Анна Сергеевна",
  email: "anna@example.ru",
  department: "Математика",
  position: "Доцент",
  is_active: true,
}

async function mockApi(page: Page, groupCount = 1) {
  let groups = Array.from({ length: groupCount }, (_, index) => ({
    ...initialGroup,
    id: index + 1,
    name: `Б05-${201 + index}`,
  }))
  let teachers = [initialTeacher]
  await page.route("**/health/ready", (route) =>
    route.fulfill({
      json: { status: "ok", database: "ok", app_name: "ScheduleService", version: "0.1" },
    }),
  )
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const match = url.pathname.match(/^\/api\/v1\/(groups|teachers)\/(\d+)?$/)
    if (!match) {
      await route.fulfill({ status: 404, json: { detail: "Not Found" } })
      return
    }
    const [, resource, id] = match
    let records: (Group | Teacher)[] = teachers
    if (resource === "groups") {
      records = groups
    }
    if (request.method() === "GET") {
      const filtered = records.filter((record) =>
        Object.entries(record).every(
          ([key, value]) =>
            !url.searchParams.has(key) || String(value) === url.searchParams.get(key),
        ),
      )
      const skip = Number(url.searchParams.get("skip") || 0)
      const limit = Number(url.searchParams.get("limit") || 100)
      await route.fulfill({ json: filtered.slice(skip, skip + limit) })
      return
    }
    if (request.method() === "DELETE") {
      groups = groups.filter((record) => record.id !== Number(id))
      teachers = teachers.filter((record) => record.id !== Number(id))
      await route.fulfill({ status: 204 })
      return
    }
    const body = request.postDataJSON()
    let recordId = records.length + 1
    if (id) {
      recordId = Number(id)
    }
    const saved = { ...metadata, ...body, id: recordId }
    records = records.filter((record) => record.id !== saved.id).concat(saved)
    if (resource === "groups") {
      groups = records as Group[]
    } else {
      teachers = records as Teacher[]
    }
    await route.fulfill({ json: saved })
  })
}

async function selectOption(page: Page, label: string, option: string) {
  await page.getByRole("combobox", { name: label, exact: true }).click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test("group creation, validation, edit and confirmed deletion", async ({ page }) => {
  await mockApi(page)
  await page.goto("/groups")
  await expect(page.getByText("Б05-201", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Добавить группу", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(dialog.getByText("Заполни поле.")).toHaveCount(2)
  await dialog.getByLabel("Шифр группы").fill("Б05-999")
  await dialog.getByLabel("Факультет").fill("Информатика")
  await dialog.getByLabel("Курс").fill("7")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(dialog.getByText("Максимальное значение: 6.")).toBeVisible()
  await dialog.getByLabel("Курс").fill("3")
  await dialog.getByLabel("Количество студентов").fill("32")
  const created = page.waitForRequest((request) => request.method() === "POST")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  expect((await created).postDataJSON()).toMatchObject({
    name: "Б05-999",
    course_number: 3,
    student_count: 32,
  })
  await expect(page.getByText("Б05-999", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Редактировать Б05-999", exact: true }).click()
  await dialog.getByLabel("Шифр группы").fill("Б05-998")
  await dialog.getByLabel("Активная запись").uncheck()
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(page.getByRole("row").filter({ hasText: "Б05-998" })).toContainText("Неактивна")
  await page.getByRole("button", { name: "Удалить Б05-998", exact: true }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Отмена", exact: true }).click()
  await expect(page.getByText("Б05-998", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Удалить Б05-998", exact: true }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Удалить", exact: true }).click()
  await expect(page.getByText("Б05-998", { exact: true })).toHaveCount(0)
})

test("teacher creation, edit and deletion use the teacher contract", async ({ page }) => {
  await mockApi(page)
  await page.goto("/teachers")
  await page.getByRole("button", { name: "Добавить преподавателя", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("ФИО").fill("Иванов Иван Иванович")
  await dialog.getByLabel("Email").fill("IVAN@example.ru")
  await dialog.getByLabel("Кафедра").fill("Информатика")
  const saved = page.waitForRequest((request) => request.method() === "POST")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  expect((await saved).postDataJSON()).toMatchObject({ email: "ivan@example.ru", position: null })
  await page
    .getByRole("button", { name: "Редактировать Иванов Иван Иванович", exact: true })
    .click()
  await dialog.getByLabel("Должность").fill("Профессор")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(page.getByRole("row").filter({ hasText: "Иванов Иван Иванович" })).toContainText(
    "Профессор",
  )
  await page.getByRole("button", { name: "Удалить Иванов Иван Иванович", exact: true }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Удалить", exact: true }).click()
  await expect(page.getByText("Иванов Иван Иванович", { exact: true })).toHaveCount(0)
})

test("pagination and server filters preserve false and reset the page", async ({ page }) => {
  await mockApi(page, 12)
  await page.goto("/groups")
  await expect(page.getByRole("row")).toHaveCount(11)
  await page.getByRole("button", { name: "Далее", exact: true }).click()
  await expect(page.getByText("Б05-211", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Далее", exact: true })).toBeDisabled()
  await page.getByLabel("Факультет", { exact: true }).fill("БИ")
  await selectOption(page, "Курс", "2 курс")
  await selectOption(page, "Статус", "Неактивные")
  const request = page.waitForRequest((request) => request.url().includes("is_active=false"))
  await page.getByRole("button", { name: "Применить", exact: true }).click()
  const query = new URL((await request).url()).searchParams
  expect(Object.fromEntries(query)).toMatchObject({
    faculty: "БИ",
    course_number: "2",
    is_active: "false",
    skip: "0",
    limit: "11",
  })
  await expect(page.getByText("Записей пока нет", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Сбросить", exact: true }).click()
  await expect(page.getByText("Б05-201", { exact: true })).toBeVisible()
})

test("409 and 422 remain in the form; 404 deletion remains actionable", async ({ page }) => {
  await mockApi(page)
  await page.goto("/teachers")
  await page
    .getByRole("button", { name: "Редактировать Смирнова Анна Сергеевна", exact: true })
    .click()
  const dialog = page.getByRole("dialog")
  await page.route("**/api/v1/teachers/1", (route) =>
    route.fulfill({ status: 409, json: { detail: "Duplicate email" } }),
  )
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(dialog.getByText("Преподаватель с таким email уже существует.")).toBeVisible()
  await expect(dialog.getByLabel("Email")).toHaveAttribute("aria-invalid", "true")
  await page.route("**/api/v1/teachers/1", (route) =>
    route.fulfill({
      status: 422,
      json: {
        detail: [
          { loc: ["body", "department"], msg: "Кафедра не существует", type: "value_error" },
        ],
      },
    }),
  )
  await dialog.getByLabel("Email").fill("new@example.ru")
  await dialog.getByRole("button", { name: "Сохранить", exact: true }).click()
  await expect(dialog.getByText("Кафедра не существует")).toBeVisible()
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click()
  await page.route("**/api/v1/teachers/1", (route) =>
    route.fulfill({ status: 404, json: { detail: "Not found" } }),
  )
  await page.getByRole("button", { name: "Удалить Смирнова Анна Сергеевна", exact: true }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Удалить", exact: true }).click()
  await expect(page.getByRole("alertdialog").getByRole("alert")).toContainText("Запись не найдена")
})

test("schedule demo filters by group, teacher, classroom and parity", async ({ page }) => {
  await mockApi(page)
  await page.goto("/schedule")
  await expect(page.getByText("Демонстрационное расписание", { exact: true })).toBeVisible()
  await expect(page.getByText("Занятий в сетке:")).toContainText("10")
  await page.screenshot({ path: "test-results/schedule-desktop.png", fullPage: true })
  await selectOption(page, "Академическая группа", "Б05-201")
  await expect(page.getByText("Занятий в сетке:")).toContainText("6")
  await page.getByRole("tab", { name: "Нечётная", exact: true }).click()
  await expect(page.getByText("Занятий в сетке:")).toContainText("4")
  await selectOption(page, "Преподаватель", "Смирнова Анна Сергеевна")
  await expect(page.getByText("Занятий в сетке:")).toContainText("2")
  await selectOption(page, "Аудитория", "Главный корпус · 201")
  await expect(page.getByText("Занятий не найдено", { exact: true })).toBeVisible()
})

test("live, empty, failed and malformed schedules never become a demo", async ({ page }) => {
  await mockApi(page)
  await page.route("**/api/v1/lessons/", (route) => route.fulfill({ json: [demoLessons[0]] }))
  await page.goto("/schedule")
  await expect(
    page.getByRole("heading", { name: "Математический анализ", exact: true }),
  ).toBeVisible()
  await expect(page.getByText("Демонстрационное расписание", { exact: true })).toHaveCount(0)
  await page.route("**/api/v1/lessons/", (route) => route.fulfill({ json: [] }))
  await page.getByRole("button", { name: "Обновить", exact: true }).click()
  await expect(page.getByText("Занятий не найдено", { exact: true })).toBeVisible()
  await page.route("**/api/v1/lessons/", (route) =>
    route.fulfill({ status: 500, body: "Internal Server Error" }),
  )
  await page.getByRole("button", { name: "Обновить", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("Ошибка сервера (500)")
  await expect(page.getByText("Демонстрационное расписание", { exact: true })).toHaveCount(0)
  await page.route("**/api/v1/lessons/", (route) => route.fulfill({ json: { items: [] } }))
  await page.getByRole("button", { name: "Повторить", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("неизвестном формате")
})

test("network failure, unavailable readiness, recovery and mobile navigation", async ({ page }) => {
  await mockApi(page)
  await page.route("**/health/ready", (route) =>
    route.fulfill({ status: 503, json: { status: "unavailable", database: "unavailable" } }),
  )
  await page.route("**/api/v1/groups/**", (route) => route.abort("failed"))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/groups")
  await expect(page.getByText("Сервис недоступен", { exact: true })).toBeVisible()
  await expect(page.getByRole("alert")).toContainText("Нет связи с сервером")
  await page.unroute("**/api/v1/groups/**")
  await page.getByRole("button", { name: "Повторить", exact: true }).click()
  await expect(page.getByText("Б05-201", { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: "test-results/groups-mobile.png", fullPage: true })
  await page.getByRole("button", { name: "Открыть навигацию", exact: true }).click()
  await page.getByRole("link", { name: "Преподаватели", exact: true }).click()
  await expect(page.getByRole("heading", { name: "Преподаватели", exact: true })).toBeVisible()
})
