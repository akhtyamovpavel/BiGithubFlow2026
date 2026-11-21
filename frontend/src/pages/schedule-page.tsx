import { Fragment, useEffect, useId, useMemo, useState } from "react"
import {
  ArrowRightLeft,
  Ban,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Download,
  Info,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  UserRound,
} from "lucide-react"
import { toast } from "sonner"
import {
  ApiError,
  classroomsApi,
  downloadExportFile,
  errorMessage,
  getAvailableClassrooms,
  getGroupSchedule,
  getLessons,
  groupsApi,
  subjectsApi,
  teachersApi,
  timeSlotsApi,
} from "@/lib/api"
import { useAuth } from "@/lib/auth"
import {
  addDaysIso,
  getIsoWeekParity,
  getWeekDates,
  isLessonScheduledOnDate,
  parseIsoDate,
  suggestOccurrenceDate,
  todayIsoDate,
} from "@/lib/dates"
import { DEMO_TIMES, demoLessons } from "@/lib/demo-schedule"
import type {
  Classroom,
  Group,
  Lesson,
  LessonType,
  OccurrenceException,
  OccurrenceExceptionAction,
  Subject,
  Teacher,
  TimeSlot,
  WeekParity,
} from "@/lib/models"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState, ErrorNotice, LoadingRows } from "@/components/feedback"
import { FilterSelect, type Option } from "@/components/filter-select"
import { formatTimeSlot, LessonDialog } from "@/components/lesson-dialog"
import { OccurrenceActionDialog } from "@/components/occurrence-action-dialog"

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
  const { canEdit } = useAuth()
  const searchFormId = useId()
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([])
  const [loading, setLoading] = useState(true)
  const [demo, setDemo] = useState(false)
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  const [parity, setParity] = useState("ALL")
  const [group, setGroup] = useState("all")
  const [teacher, setTeacher] = useState("all")
  const [classroom, setClassroom] = useState("all")
  const [addingLesson, setAddingLesson] = useState(false)
  const [exporting, setExporting] = useState<"ics" | "csv" | null>(null)
  const [selectedDate, setSelectedDate] = useState("")
  const [exceptionsByLesson, setExceptionsByLesson] = useState<
    Record<number, OccurrenceException[]>
  >({})
  const [selectedOccurrence, setSelectedOccurrence] = useState<{
    lesson: Lesson
    action: OccurrenceExceptionAction
    date: string
  } | null>(null)

  const [searchSlotId, setSearchSlotId] = useState("")
  const [minCapacity, setMinCapacity] = useState("")
  const [availableRooms, setAvailableRooms] = useState<Classroom[] | null>(null)
  const [searchingRooms, setSearchingRooms] = useState(false)
  const [searchError, setSearchError] = useState("")

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError("")
    setDemo(false)

    void Promise.all([
      groupsApi.list({ limit: 100 }, controller.signal).catch(() => [] as Group[]),
      teachersApi.list({ limit: 100 }, controller.signal).catch(() => [] as Teacher[]),
      classroomsApi.list({ limit: 100 }, controller.signal).catch(() => [] as Classroom[]),
      subjectsApi.list({ limit: 100 }, controller.signal).catch(() => [] as Subject[]),
      timeSlotsApi.list({ limit: 100 }, controller.signal).catch(() => [] as TimeSlot[]),
    ]).then(([loadedGroups, loadedTeachers, loadedClassrooms, loadedSubjects, loadedSlots]) => {
      if (controller.signal.aborted) return
      setGroups(loadedGroups)
      setTeachers(loadedTeachers)
      setClassrooms(loadedClassrooms)
      setSubjects(loadedSubjects)
      setTimeSlots(loadedSlots)
      if (loadedSlots.length > 0) {
        setSearchSlotId((prev) => prev || String(loadedSlots[0].id))
      }
      void Promise.all(
        loadedGroups.map((g) => getGroupSchedule(g.id, {}, controller.signal).catch(() => null)),
      ).then((schedules) => {
        if (controller.signal.aborted) return
        const map: Record<number, OccurrenceException[]> = {}
        for (const schedule of schedules) {
          if (!schedule) continue
          for (const day of schedule.days) {
            for (const item of day.lessons) {
              if (item.exceptions?.length) map[item.id] = item.exceptions
            }
          }
        }
        setExceptionsByLesson(map)
      })
    })

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

  const weekDays = useMemo(
    () => (parseIsoDate(selectedDate) ? getWeekDates(selectedDate) : null),
    [selectedDate],
  )
  const replacementIds = useMemo(() => {
    const ids = new Set<number>()
    for (const list of Object.values(exceptionsByLesson)) {
      for (const exc of list) {
        if (exc.replacement_lesson_id !== null) ids.add(exc.replacement_lesson_id)
      }
    }
    return ids
  }, [exceptionsByLesson])

  const lessonsWithExceptions = useMemo(
    () => lessons.map((l) => ({ ...l, exceptions: exceptionsByLesson[l.id] || l.exceptions || [] })),
    [exceptionsByLesson, lessons],
  )

  async function handleSearchAvailable(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!searchSlotId) return
    setSearchingRooms(true)
    setSearchError("")
    try {
      const cap = minCapacity.trim() ? Number(minCapacity.trim()) : undefined
      const selectedParity: WeekParity =
        parity === "ODD_WEEK" || parity === "EVEN_WEEK" ? parity : "ALWAYS"
      const slot = timeSlots.find((s) => String(s.id) === searchSlotId)
      const slotDate = weekDays?.find((d) => d.dayOfWeek === slot?.day_of_week)?.iso
      const rooms = await getAvailableClassrooms({
        time_slot_id: Number(searchSlotId),
        parity: selectedParity,
        date: slotDate,
        min_capacity: cap && cap > 0 ? cap : undefined,
      })
      setAvailableRooms(rooms)
    } catch (failure) {
      setSearchError(errorMessage(failure))
      setAvailableRooms([])
    } finally {
      setSearchingRooms(false)
    }
  }

  const baseFiltered = lessonsWithExceptions.filter(
    (lesson) =>
      (group === "all" || String(lesson.group_id) === group) &&
      (teacher === "all" || String(lesson.teacher_id) === teacher) &&
      (classroom === "all" || String(lesson.classroom_id) === classroom),
  )

  const filtered = baseFiltered.filter((lesson) => {
    if (weekDays) {
      return weekDays.some(
        (day) =>
          isLessonScheduledOnDate(lesson, day.iso) &&
          !lesson.exceptions.some((exc) => exc.occurrence_date === day.iso),
      )
    }
    if (replacementIds.has(lesson.id)) {
      return false
    }
    return (
      parity === "ALL" ||
      lesson.parity === "ALWAYS" ||
      lesson.parity === parity ||
      !!lesson.specific_date
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

  const defaultGroupId = groups[0]?.id ?? lessons[0]?.group_id ?? 1
  const exportScope =
    group !== "all"
      ? `group/${group}`
      : teacher !== "all"
        ? `teacher/${teacher}`
        : `group/${defaultGroupId}`
  const exportFilenamePrefix =
    group !== "all"
      ? `schedule_group_${group}`
      : teacher !== "all"
        ? `schedule_teacher_${teacher}`
        : `schedule_group_${defaultGroupId}`

  async function handleExport(format: "ics" | "csv") {
    setExporting(format)
    try {
      await downloadExportFile(
        `/schedule/${exportScope}/export/${format}`,
        `${exportFilenamePrefix}.${format}`,
      )
    } catch (failure) {
      toast.error(errorMessage(failure))
    } finally {
      setExporting(null)
    }
  }

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
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={exporting !== null}
            onClick={() => void handleExport("ics")}
          >
            <Download aria-hidden="true" />
            Скачать .ics
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={exporting !== null}
            onClick={() => void handleExport("csv")}
          >
            <Download aria-hidden="true" />
            Скачать .csv
          </Button>
          <Button
            variant="outline"
            disabled={loading}
            onClick={() => setRevision((value) => value + 1)}
          >
            <RefreshCw aria-hidden="true" />
            Обновить
          </Button>
          {canEdit && (
            <Button onClick={() => setAddingLesson(true)}>
              <Plus aria-hidden="true" />
              Добавить занятие
            </Button>
          )}
        </div>
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
        <div className="flex flex-wrap items-center gap-3">
          {!weekDays && (
            <Tabs value={parity} onValueChange={setParity} aria-label="Тип недели">
              <TabsList>
                <TabsTrigger value="ALL">Все недели</TabsTrigger>
                <TabsTrigger value="ODD_WEEK">Нечётная</TabsTrigger>
                <TabsTrigger value="EVEN_WEEK">Чётная</TabsTrigger>
              </TabsList>
            </Tabs>
          )}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-1.5">
            <Label htmlFor={`${searchFormId}-week-date`} className="text-xs text-muted-foreground">
              Дата недели
            </Label>
            <Input
              id={`${searchFormId}-week-date`}
              type="date"
              aria-label="Дата учебной недели"
              value={selectedDate}
              onChange={(event) => setSelectedDate(event.target.value)}
              className="h-8 w-40"
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="size-8"
              aria-label="Предыдущая неделя"
              onClick={() => setSelectedDate(addDaysIso(selectedDate || todayIsoDate(), -7))}
            >
              <ChevronLeft className="size-4" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="size-8"
              aria-label="Следующая неделя"
              onClick={() => setSelectedDate(addDaysIso(selectedDate || todayIsoDate(), 7))}
            >
              <ChevronRight className="size-4" aria-hidden="true" />
            </Button>
            {weekDays && (
              <>
                <Badge variant="secondary" className="font-normal">
                  {weekDays[0].shortDate}–{weekDays[5].shortDate} ·{" "}
                  {getIsoWeekParity(selectedDate) === "ODD_WEEK" ? "Нечётная" : "Чётная"}
                </Badge>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  onClick={() => setSelectedDate("")}
                >
                  Все недели
                </Button>
              </>
            )}
          </div>
        </div>
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
              {days.map((day, dayIndex) => {
                const dayInfo = weekDays?.[dayIndex]
                const isSelectedDay = !!dayInfo && dayInfo.iso === selectedDate
                return (
                  <div
                    role="columnheader"
                    key={day}
                    className={cn(
                      "border-l px-3 py-4 text-sm font-medium",
                      isSelectedDay && "bg-primary/10 text-primary",
                    )}
                  >
                    {day}
                    {dayInfo && (
                      <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                        {dayInfo.shortDate}
                      </span>
                    )}
                  </div>
                )
              })}
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
                {days.map((day, dayIndex) => {
                  const dayInfo = weekDays?.[dayIndex]
                  const cellLessons = visible.filter((lesson) =>
                    dayInfo
                      ? lesson.time_slot?.slot_number === index + 1 &&
                        isLessonScheduledOnDate(lesson, dayInfo.iso) &&
                        !lesson.exceptions.some((exc) => exc.occurrence_date === dayInfo.iso)
                      : lesson.time_slot?.day_of_week === dayIndex + 1 &&
                        lesson.time_slot.slot_number === index + 1,
                  )
                  const suppressed = dayInfo
                    ? baseFiltered
                        .filter(
                          (lesson) =>
                            lesson.time_slot?.slot_number === index + 1 &&
                            isLessonScheduledOnDate(lesson, dayInfo.iso),
                        )
                        .map((lesson) => ({
                          lesson,
                          exc: lesson.exceptions.find((e) => e.occurrence_date === dayInfo.iso),
                        }))
                        .filter(
                          (item): item is { lesson: (typeof baseFiltered)[number]; exc: OccurrenceException } =>
                            !!item.exc,
                        )
                    : []
                  return (
                    <div
                      role="cell"
                      key={day}
                      className="min-h-32 space-y-2 border-l bg-muted/10 p-2"
                    >
                      {cellLessons.map((lesson) => {
                        const isReplacement = replacementIds.has(lesson.id)
                        const subjectName =
                          lesson.subject?.name || `Дисциплина #${lesson.subject_id}`
                        const groupName = lesson.group?.name || `Группа #${lesson.group_id}`
                        const occDate = dayInfo?.iso || suggestOccurrenceDate(lesson, selectedDate)
                        return (
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
                                  {isReplacement && (
                                    <Badge
                                      variant="outline"
                                      className="border-primary/40 bg-primary/10 px-1.5 text-[10px] text-primary"
                                    >
                                      Перенесено
                                    </Badge>
                                  )}
                                  {!weekDays && lesson.exceptions.length > 0 && (
                                    <Badge variant="outline" className="px-1.5 text-[10px]">
                                      Исключений: {lesson.exceptions.length}
                                    </Badge>
                                  )}
                                </div>
                                <h2 className="text-sm leading-snug font-semibold">
                                  {subjectName}
                                </h2>
                                <p className="flex items-start gap-1.5 text-muted-foreground">
                                  <UserRound className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                                  {lesson.teacher?.full_name || `Преподаватель #${lesson.teacher_id}`}
                                </p>
                                <p className="flex items-center gap-1.5 text-muted-foreground">
                                  <BookOpen className="size-3 shrink-0" aria-hidden="true" />
                                  {groupName}
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
                                {canEdit && !demo && !isReplacement && (
                                  <div className="flex flex-wrap gap-1 pt-1">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      className="h-7 px-2 text-[11px]"
                                      aria-label={`Перенести ${subjectName} (${groupName})`}
                                      onClick={() =>
                                        setSelectedOccurrence({
                                          lesson,
                                          action: "move",
                                          date: occDate,
                                        })
                                      }
                                    >
                                      <ArrowRightLeft className="size-3" aria-hidden="true" />
                                      Перенести
                                    </Button>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      className="h-7 px-2 text-[11px] text-destructive hover:text-destructive"
                                      aria-label={`Отменить ${subjectName} (${groupName})`}
                                      onClick={() =>
                                        setSelectedOccurrence({
                                          lesson,
                                          action: "cancel",
                                          date: occDate,
                                        })
                                      }
                                    >
                                      <Ban className="size-3" aria-hidden="true" />
                                      Отменить
                                    </Button>
                                  </div>
                                )}
                              </CardContent>
                            </Card>
                          </Fragment>
                        )
                      })}
                      {suppressed.map(({ lesson, exc }) => (
                        <div
                          key={`exc-${lesson.id}-${exc.occurrence_date}`}
                          className="rounded-md border border-dashed bg-muted/40 px-2.5 py-1.5 text-[11px] text-muted-foreground"
                        >
                          {exc.action === "cancel" ? "Отменено" : "Перенесено"}:{" "}
                          {lesson.subject?.name || `Дисциплина #${lesson.subject_id}`} (
                          {lesson.group?.name || `Группа #${lesson.group_id}`})
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      <section
        aria-label="Поиск свободных аудиторий"
        className="space-y-4 rounded-xl border bg-card p-5"
      >
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Поиск свободных аудиторий</h2>
          <p className="text-sm text-muted-foreground">
            Подбор незанятых аудиторий на выбранный временной слот с учётом минимальной вместимости.
          </p>
        </div>
        <form onSubmit={handleSearchAvailable} className="flex flex-wrap items-end gap-4">
          <div className="min-w-64 flex-1 space-y-2">
            <Label htmlFor={`${searchFormId}-slot`}>Слот для поиска аудитории</Label>
            <select
              id={`${searchFormId}-slot`}
              value={searchSlotId}
              onChange={(event) => setSearchSlotId(event.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs"
            >
              {timeSlots.map((slot) => (
                <option key={slot.id} value={String(slot.id)}>
                  {formatTimeSlot(slot)}
                </option>
              ))}
            </select>
          </div>
          <div className="w-56 space-y-2">
            <Label htmlFor={`${searchFormId}-cap`}>Минимальная вместимость</Label>
            <Input
              id={`${searchFormId}-cap`}
              type="number"
              min={1}
              step={1}
              value={minCapacity}
              onChange={(event) => setMinCapacity(event.target.value)}
              placeholder="Например, 50"
            />
          </div>
          <Button type="submit" variant="secondary" disabled={searchingRooms || !searchSlotId}>
            <Search aria-hidden="true" />
            Найти свободные аудитории
          </Button>
        </form>

        {searchError && <ErrorNotice message={searchError} />}
        {availableRooms !== null && !searchError && (
          <div className="space-y-2 pt-2">
            {availableRooms.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Свободных аудиторий по заданным критериям не найдено.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {availableRooms.map((room) => (
                  <div
                    key={room.id}
                    className="flex items-center justify-between rounded-lg border bg-background p-3 text-sm"
                  >
                    <div>
                      <p className="font-medium">
                        {room.building} · {room.room_number}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {room.has_projector ? "Проектор" : "Без проектора"}
                        {room.has_computers ? " · Компьютеры" : ""}
                      </p>
                    </div>
                    <Badge variant="secondary">{room.capacity} мест</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {canEdit && addingLesson && (
        <LessonDialog
          groups={groups}
          teachers={teachers}
          classrooms={classrooms}
          subjects={subjects}
          timeSlots={timeSlots}
          onClose={() => setAddingLesson(false)}
          onSaved={() => setRevision((value) => value + 1)}
        />
      )}
      {canEdit && selectedOccurrence && (
        <OccurrenceActionDialog
          lesson={selectedOccurrence.lesson}
          initialAction={selectedOccurrence.action}
          initialDate={selectedOccurrence.date}
          classrooms={classrooms}
          timeSlots={timeSlots}
          onClose={() => setSelectedOccurrence(null)}
          onSaved={() => setRevision((value) => value + 1)}
        />
      )}
    </div>
  )
}
