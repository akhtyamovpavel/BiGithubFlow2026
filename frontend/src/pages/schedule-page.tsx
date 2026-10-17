import { Fragment, useEffect, useState } from "react"
import { BookOpen, Info, MapPin, RefreshCw, UserRound } from "lucide-react"
import { ApiError, errorMessage, getLessons } from "@/lib/api"
import { DEMO_TIMES, demoLessons } from "@/lib/demo-schedule"
import type { Lesson, LessonType, WeekParity } from "@/lib/models"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState, ErrorNotice, LoadingRows } from "@/components/feedback"
import { FilterSelect, type Option } from "@/components/filter-select"

const days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
const typeLabels: Record<LessonType, string> = {
  LECTURE: "Лекция",
  SEMINAR: "Семинар",
  LAB: "Практикум",
}
const parityLabels: Record<WeekParity, string> = {
  ALWAYS: "Каждую неделю",
  ODD_WEEK: "Нечётная",
  EVEN_WEEK: "Чётная",
}

function optionsFor(lessons: Lesson[], resource: "group" | "teacher" | "classroom"): Option[] {
  const values = new Map<string, string>()
  for (const lesson of lessons) {
    if (resource === "group") {
      values.set(String(lesson.group_id), lesson.group?.name || `Группа #${lesson.group_id}`)
    }
    if (resource === "teacher") {
      values.set(
        String(lesson.teacher_id),
        lesson.teacher?.full_name || `Преподаватель #${lesson.teacher_id}`,
      )
    }
    if (resource === "classroom") {
      let label = `Аудитория #${lesson.classroom_id}`
      if (lesson.classroom) {
        label = `${lesson.classroom.building} · ${lesson.classroom.room_number}`
      }
      values.set(String(lesson.classroom_id), label)
    }
  }
  return [
    { value: "all", label: "Все" },
    ...Array.from(values, ([value, label]) => ({ value, label })),
  ]
}

export function SchedulePage() {
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [loading, setLoading] = useState(true)
  const [demo, setDemo] = useState(false)
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  const [parity, setParity] = useState("ALL")
  const [group, setGroup] = useState("all")
  const [teacher, setTeacher] = useState("all")
  const [classroom, setClassroom] = useState("all")

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError("")
    setDemo(false)
    setGroup("all")
    setTeacher("all")
    setClassroom("all")
    getLessons(controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) {
          setLessons(records)
        }
      })
      .catch((failure) => {
        if (controller.signal.aborted) {
          return
        }
        if (failure instanceof ApiError && (failure.status === 404 || failure.status === 501)) {
          setLessons(demoLessons)
          setDemo(true)
        } else {
          setLessons([])
          setError(errorMessage(failure))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [revision])

  const filtered = lessons.filter((lesson) => {
    const weekMatches =
      parity === "ALL" ||
      lesson.parity === "ALWAYS" ||
      lesson.parity === parity ||
      !!lesson.specific_date
    return (
      weekMatches &&
      (group === "all" || String(lesson.group_id) === group) &&
      (teacher === "all" || String(lesson.teacher_id) === teacher) &&
      (classroom === "all" || String(lesson.classroom_id) === classroom)
    )
  })
  const visible = filtered.filter(
    (lesson) =>
      lesson.time_slot &&
      lesson.time_slot.day_of_week <= 6 &&
      lesson.time_slot.day_of_week >= 1 &&
      lesson.time_slot.slot_number >= 1 &&
      lesson.time_slot.slot_number <= 6,
  )
  const unplaced = filtered.length - visible.length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-primary">Планирование занятий</p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Сетка расписания</h1>
          <p className="text-sm text-muted-foreground">
            Учебная неделя, с понедельника по субботу.
          </p>
        </div>
        <Button
          variant="outline"
          disabled={loading}
          onClick={() => setRevision((value) => value + 1)}
        >
          <RefreshCw aria-hidden="true" />
          Обновить
        </Button>
      </div>

      {demo && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm"
        >
          <Info className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold">Демонстрационное расписание</p>
            <p className="text-muted-foreground">
              Показаны вымышленные занятия для знакомства с сеткой. Они не сохранены в сервисе.
            </p>
          </div>
          <Badge variant="outline" className="ml-auto hidden sm:inline-flex">
            Демо
          </Badge>
        </div>
      )}

      <div className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-3">
        <FilterSelect
          label="Академическая группа"
          value={group}
          onChange={setGroup}
          options={optionsFor(lessons, "group")}
          disabled={loading || !!error}
        />
        <FilterSelect
          label="Преподаватель"
          value={teacher}
          onChange={setTeacher}
          options={optionsFor(lessons, "teacher")}
          disabled={loading || !!error}
        />
        <FilterSelect
          label="Аудитория"
          value={classroom}
          onChange={setClassroom}
          options={optionsFor(lessons, "classroom")}
          disabled={loading || !!error}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={parity} onValueChange={setParity} aria-label="Тип недели">
          <TabsList>
            <TabsTrigger value="ALL">Все недели</TabsTrigger>
            <TabsTrigger value="ODD_WEEK">Нечётная</TabsTrigger>
            <TabsTrigger value="EVEN_WEEK">Чётная</TabsTrigger>
          </TabsList>
        </Tabs>
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Занятий в сетке:{" "}
          <span className="font-medium tabular-nums text-foreground">{visible.length}</span>
        </p>
      </div>

      {loading && <LoadingRows />}
      {!loading && error && (
        <ErrorNotice message={error} retry={() => setRevision((value) => value + 1)} />
      )}
      {!loading && !error && unplaced > 0 && (
        <ErrorNotice
          message={`Вне сетки: ${unplaced}. Время занятия не указано или пара выходит за диапазон Пн–Сб, 1–6.`}
        />
      )}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          title="Занятий не найдено"
          description="Для выбранных фильтров занятий нет. Можно выбрать другую группу, преподавателя или тип недели."
        />
      )}
      {!loading && !error && (
        <p className="text-xs text-muted-foreground 2xl:hidden">
          Сетку можно прокручивать по горизонтали.
        </p>
      )}
      {!loading && !error && (
        <div
          className="overflow-x-auto rounded-xl border bg-card"
          role="region"
          aria-label="Недельная сетка расписания"
          tabIndex={0}
        >
          <div role="table" aria-label="Расписание по дням и парам" className="min-w-[1120px]">
            <div role="row" className="schedule-row border-b bg-muted/40">
              <div role="columnheader" className="p-4 text-xs font-medium text-muted-foreground">
                Пара
              </div>
              {days.map((day) => (
                <div
                  role="columnheader"
                  key={day}
                  className="border-l px-3 py-4 text-sm font-medium"
                >
                  {day}
                </div>
              ))}
            </div>
            {Array.from({ length: 6 }, (_, index) => (
              <div role="row" key={index} className="schedule-row border-b last:border-b-0">
                <div role="rowheader" className="space-y-2 px-3 py-4 text-center">
                  <p className="text-lg font-semibold tabular-nums">{index + 1}</p>
                  {demo && (
                    <p className="text-[11px] leading-relaxed text-muted-foreground">
                      {DEMO_TIMES[index][0]}
                      <br />
                      {DEMO_TIMES[index][1]}
                    </p>
                  )}
                </div>
                {days.map((day, dayIndex) => (
                  <div
                    role="cell"
                    key={day}
                    className="min-h-32 space-y-2 border-l bg-muted/10 p-2"
                  >
                    {visible
                      .filter(
                        (lesson) =>
                          lesson.time_slot?.day_of_week === dayIndex + 1 &&
                          lesson.time_slot.slot_number === index + 1,
                      )
                      .map((lesson) => (
                        <Fragment key={lesson.id}>
                          <Card className="gap-0 rounded-lg border-l-[3px] border-l-primary py-0 shadow-none">
                            <CardContent className="space-y-2 p-3 text-xs">
                              <div className="flex flex-wrap gap-1">
                                <Badge variant="secondary" className="px-1.5 text-[10px]">
                                  {typeLabels[lesson.lesson_type]}
                                </Badge>
                                <Badge variant="outline" className="px-1.5 text-[10px]">
                                  {parityLabels[lesson.parity]}
                                </Badge>
                              </div>
                              <h2 className="text-sm leading-snug font-semibold">
                                {lesson.subject?.name || `Дисциплина #${lesson.subject_id}`}
                              </h2>
                              <p className="flex items-start gap-1.5 text-muted-foreground">
                                <UserRound className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                                {lesson.teacher?.full_name || `Преподаватель #${lesson.teacher_id}`}
                              </p>
                              <p className="flex items-center gap-1.5 text-muted-foreground">
                                <BookOpen className="size-3 shrink-0" aria-hidden="true" />
                                {lesson.group?.name || `Группа #${lesson.group_id}`}
                              </p>
                              <p className="flex items-start gap-1.5 text-muted-foreground">
                                <MapPin className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                                {lesson.classroom?.room_number ||
                                  `Аудитория #${lesson.classroom_id}`}
                              </p>
                              {!demo && lesson.time_slot && (
                                <p className="text-muted-foreground">
                                  {lesson.time_slot.start_time.slice(0, 5)}–
                                  {lesson.time_slot.end_time.slice(0, 5)}
                                </p>
                              )}
                              {lesson.specific_date && (
                                <p className="font-medium">{lesson.specific_date}</p>
                              )}
                            </CardContent>
                          </Card>
                        </Fragment>
                      ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="text-xs leading-relaxed text-muted-foreground">
        Сетка доступна для просмотра. Создание занятий пока недоступно.
      </p>
    </div>
  )
}
