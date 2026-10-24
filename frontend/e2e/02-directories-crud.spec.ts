import { expect, test, type APIRequestContext } from "@playwright/test"

const TEST_GROUP_NAME = "Б05-909"
const TEST_TEACHER_NAME = "Петров Алексей Владимирович"
const TEST_TEACHER_EMAIL = "a.petrov.e2e@phystech.edu"
const TEST_CLASSROOM_BUILDING = "КПМ"
const TEST_CLASSROOM_NUMBER = "909"
const TEST_SUBJECT_NAME = "Автоматизированное E2E-тестирование"
const TEST_SUBJECT_CODE = "QA-909"

async function cleanupTestEntities(request: APIRequestContext) {
  const groupsRes = await request.get("/api/v1/groups/?limit=200")
  if (groupsRes.ok()) {
    const groups = (await groupsRes.json()) as Array<{ id: number; name: string }>
    for (const group of groups.filter((item) => item.name === TEST_GROUP_NAME)) {
      await request.delete(`/api/v1/groups/${group.id}`)
    }
  }

  const teachersRes = await request.get("/api/v1/teachers/?limit=200")
  if (teachersRes.ok()) {
    const teachers = (await teachersRes.json()) as Array<{ id: number; email: string }>
    for (const teacher of teachers.filter((item) => item.email === TEST_TEACHER_EMAIL)) {
      await request.delete(`/api/v1/teachers/${teacher.id}`)
    }
  }

  const classroomsRes = await request.get("/api/v1/classrooms/?limit=200")
  if (classroomsRes.ok()) {
    const classrooms = (await classroomsRes.json()) as Array<{
      id: number
      building: string
      room_number: string
    }>
    for (const room of classrooms.filter(
      (item) =>
        item.building === TEST_CLASSROOM_BUILDING && item.room_number === TEST_CLASSROOM_NUMBER,
    )) {
      await request.delete(`/api/v1/classrooms/${room.id}`)
    }
  }

  const subjectsRes = await request.get("/api/v1/subjects/?limit=200")
  if (subjectsRes.ok()) {
    const subjects = (await subjectsRes.json()) as Array<{
      id: number
      name: string
      code: string | null
    }>
    for (const subject of subjects.filter(
      (item) => item.name === TEST_SUBJECT_NAME || item.code === TEST_SUBJECT_CODE,
    )) {
      await request.delete(`/api/v1/subjects/${subject.id}`)
    }
  }
}

test.describe("Сценарий 2 — Управление справочниками (CRUD)", () => {
  test.beforeEach(async ({ request }) => {
    await cleanupTestEntities(request)
  })

  test.afterEach(async ({ request }) => {
    await cleanupTestEntities(request)
  })

  test("создание учебной группы, преподавателя, аудитории и предмета через модальные окна UI", async ({
    page,
  }) => {
    // 1. Создание новой учебной группы
    await page.goto("/groups")
    await expect(
      page.getByRole("heading", { name: "Академические группы", exact: true }),
    ).toBeVisible()
    await page.getByRole("button", { name: "Добавить группу", exact: true }).click()

    const groupDialog = page.getByRole("dialog")
    await expect(groupDialog).toBeVisible()
    await groupDialog.getByLabel("Шифр группы").fill(TEST_GROUP_NAME)
    await groupDialog.getByLabel("Факультет").fill("ФПМИ")
    await groupDialog.getByLabel("Курс").fill("4")
    await groupDialog.getByLabel("Количество студентов").fill("27")
    await groupDialog.getByRole("button", { name: "Сохранить", exact: true }).click()

    await expect(groupDialog).toHaveCount(0)
    const groupRow = page.getByRole("row").filter({ hasText: TEST_GROUP_NAME })
    await expect(groupRow).toBeVisible()
    await expect(groupRow).toContainText("ФПМИ")
    await expect(groupRow).toContainText("4 курс · 27 чел.")

    // 2. Создание нового преподавателя
    await page.getByRole("link", { name: "Преподаватели", exact: true }).click()
    await expect(page.getByRole("heading", { name: "Преподаватели", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Добавить преподавателя", exact: true }).click()

    const teacherDialog = page.getByRole("dialog")
    await expect(teacherDialog).toBeVisible()
    await teacherDialog.getByLabel("ФИО").fill(TEST_TEACHER_NAME)
    await teacherDialog.getByLabel("Email").fill(TEST_TEACHER_EMAIL)
    await teacherDialog.getByLabel("Кафедра").fill("Кафедра системного программирования")
    await teacherDialog.getByLabel("Должность").fill("Доцент")
    await teacherDialog.getByRole("button", { name: "Сохранить", exact: true }).click()

    await expect(teacherDialog).toHaveCount(0)
    const teacherRow = page.getByRole("row").filter({ hasText: TEST_TEACHER_NAME })
    await expect(teacherRow).toBeVisible()
    await expect(teacherRow).toContainText(TEST_TEACHER_EMAIL)
    await expect(teacherRow).toContainText("Доцент")

    // 3. Создание новой аудитории
    await page.getByRole("link", { name: "Аудитории", exact: true }).click()
    await expect(page.getByRole("heading", { name: "Аудитории", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Добавить аудиторию", exact: true }).click()

    const classroomDialog = page.getByRole("dialog")
    await expect(classroomDialog).toBeVisible()
    await classroomDialog.getByLabel("Корпус").fill(TEST_CLASSROOM_BUILDING)
    await classroomDialog.getByLabel("Номер аудитории").fill(TEST_CLASSROOM_NUMBER)
    await classroomDialog.getByLabel("Вместимость").fill("45")
    await classroomDialog.getByLabel("Проектор").check()
    await classroomDialog.getByRole("button", { name: "Сохранить", exact: true }).click()

    await expect(classroomDialog).toHaveCount(0)
    const classroomRow = page
      .getByRole("row")
      .filter({ hasText: `${TEST_CLASSROOM_BUILDING} · ${TEST_CLASSROOM_NUMBER}` })
    await expect(classroomRow).toBeVisible()
    await expect(classroomRow).toContainText("45 мест")

    // 4. Создание нового предмета
    await page.getByRole("link", { name: "Предметы", exact: true }).click()
    await expect(page.getByRole("heading", { name: "Предметы", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Добавить предмет", exact: true }).click()

    const subjectDialog = page.getByRole("dialog")
    await expect(subjectDialog).toBeVisible()
    await subjectDialog.getByLabel("Название предмета").fill(TEST_SUBJECT_NAME)
    await subjectDialog.getByLabel("Код дисциплины").fill(TEST_SUBJECT_CODE)
    await subjectDialog
      .getByLabel("Описание")
      .fill("Сквозное тестирование веб-приложений с помощью Playwright")
    await subjectDialog.getByRole("button", { name: "Сохранить", exact: true }).click()

    await expect(subjectDialog).toHaveCount(0)
    const subjectRow = page.getByRole("row").filter({ hasText: TEST_SUBJECT_NAME })
    await expect(subjectRow).toBeVisible()
    await expect(subjectRow).toContainText(TEST_SUBJECT_CODE)
  })
})
