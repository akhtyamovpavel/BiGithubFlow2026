import { useEffect, useId, useState } from "react"
import { ChevronLeft, ChevronRight, Pencil, Plus, Trash2, Users, GraduationCap } from "lucide-react"
import { toast } from "sonner"
import { errorMessage, groupsApi, teachersApi } from "@/lib/api"
import type { DirectoryRecord, GroupFilters, TeacherFilters, Resource } from "@/lib/models"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { EmptyState, ErrorNotice, LoadingRows } from "@/components/feedback"
import { FilterSelect } from "@/components/filter-select"
import { RecordDialog } from "@/components/record-dialog"

const PAGE_SIZE = 10
const activeOptions = [
  { value: "all", label: "Все записи" },
  { value: "true", label: "Активные" },
  { value: "false", label: "Неактивные" },
]
const courseOptions = [
  { value: "all", label: "Все курсы" },
  ...Array.from({ length: 6 }, (_, index) => ({
    value: String(index + 1),
    label: `${index + 1} курс`,
  })),
]

function recordName(record: DirectoryRecord): string {
  if ("name" in record) {
    return record.name
  }
  return record.full_name
}

export function DirectoryPage({ resource }: { resource: Resource }) {
  const isGroup = resource === "groups"
  const fieldId = useId()
  const [rows, setRows] = useState<DirectoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [term, setTerm] = useState("")
  const [course, setCourse] = useState("all")
  const [active, setActive] = useState("all")
  const [filters, setFilters] = useState({ term: "", course: "all", active: "all" })
  const [editing, setEditing] = useState<DirectoryRecord | null | undefined>()
  const [deleting, setDeleting] = useState<DirectoryRecord | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  let title = "Преподаватели"
  let description = "Контакты, кафедры и участие в учебном процессе."
  let addLabel = "Добавить преподавателя"
  let filterLabel = "Кафедра"
  let Icon = GraduationCap
  if (isGroup) {
    title = "Академические группы"
    description = "Состав групп и направления подготовки для планирования занятий."
    addLabel = "Добавить группу"
    filterLabel = "Факультет"
    Icon = Users
  }

  const params: GroupFilters & TeacherFilters = { skip: page * PAGE_SIZE, limit: PAGE_SIZE + 1 }
  if (filters.active !== "all") {
    params.is_active = filters.active === "true"
  }
  if (isGroup && filters.course !== "all") {
    params.course_number = Number(filters.course)
  }
  if (filters.term) {
    if (isGroup) {
      params.faculty = filters.term
    } else {
      params.department = filters.term
    }
  }
  const query = JSON.stringify(params)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError("")
    const params = JSON.parse(query) as GroupFilters & TeacherFilters
    let promise: Promise<DirectoryRecord[]>
    if (resource === "groups") {
      promise = groupsApi.list(params, controller.signal)
    } else {
      promise = teachersApi.list(params, controller.signal)
    }
    promise
      .then((records) => {
        if (!controller.signal.aborted) {
          setRows(records.slice(0, PAGE_SIZE))
          setHasNext(records.length > PAGE_SIZE)
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setRows([])
          setError(errorMessage(failure))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [query, resource, revision])

  function refresh() {
    setRevision((value) => value + 1)
  }

  async function remove() {
    if (!deleting) {
      return
    }
    setDeleteBusy(true)
    setDeleteError("")
    try {
      if (isGroup) {
        await groupsApi.remove(deleting.id)
      } else {
        await teachersApi.remove(deleting.id)
      }
      setDeleting(null)
      toast.success("Запись удалена")
      if (rows.length === 1 && page > 0) {
        setPage((value) => value - 1)
      }
      refresh()
    } catch (failure) {
      setDeleteError(errorMessage(failure))
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-primary">Справочники</p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">{description}</p>
        </div>
        <Button onClick={() => setEditing(null)}>
          <Plus aria-hidden="true" />
          {addLabel}
        </Button>
      </div>

      <section className="overflow-hidden rounded-xl border bg-card" aria-label={title}>
        <form
          className="flex flex-wrap items-end gap-3 border-b bg-muted/30 p-5"
          onSubmit={(event) => {
            event.preventDefault()
            setPage(0)
            setFilters({ term: term.trim(), course, active })
          }}
        >
          <div className="min-w-44 flex-1 space-y-2">
            <Label htmlFor={fieldId}>{filterLabel}</Label>
            <Input
              id={fieldId}
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Точное название"
              className="bg-background"
            />
          </div>
          {isGroup && (
            <FilterSelect
              label="Курс"
              value={course}
              onChange={setCourse}
              options={courseOptions}
            />
          )}
          <FilterSelect
            label="Статус"
            value={active}
            onChange={setActive}
            options={activeOptions}
          />
          <Button type="submit" variant="secondary">
            Применить
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setTerm("")
              setCourse("all")
              setActive("all")
              setFilters({ term: "", course: "all", active: "all" })
              setPage(0)
            }}
          >
            Сбросить
          </Button>
        </form>

        {loading && <LoadingRows />}
        {!loading && error && (
          <div className="p-5">
            <ErrorNotice message={error} retry={refresh} />
          </div>
        )}
        {!loading && !error && rows.length === 0 && (
          <EmptyState
            title="Записей пока нет"
            description="Добавь первую запись или измени фильтры, если справочник уже заполнен."
          />
        )}
        {!loading && !error && rows.length > 0 && (
          <div>
            <p className="border-b px-5 py-2 text-xs text-muted-foreground md:hidden">
              Таблицу можно прокручивать по горизонтали.
            </p>
            <Table className="min-w-[720px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">
                    {isGroup && "Группа"}
                    {!isGroup && "Преподаватель"}
                  </TableHead>
                  <TableHead>{filterLabel}</TableHead>
                  <TableHead>
                    {isGroup && "Курс / студенты"}
                    {!isGroup && "Должность"}
                  </TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="pr-5 text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell className="py-4 pl-5">
                      <div className="flex items-center gap-3">
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/7 text-primary">
                          <Icon className="size-4" aria-hidden="true" />
                        </span>
                        <div className="whitespace-normal">
                          <p className="font-medium">{recordName(record)}</p>
                          {"email" in record && (
                            <p className="mt-1 text-xs text-muted-foreground">{record.email}</p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-56 whitespace-normal text-muted-foreground">
                      {"faculty" in record && record.faculty}
                      {"department" in record && record.department}
                    </TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {"course_number" in record &&
                        `${record.course_number} курс · ${record.student_count} чел.`}
                      {"position" in record && (record.position || "Не указана")}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(record.is_active && "bg-primary/10 text-primary")}
                      >
                        {record.is_active && "Активна"}
                        {!record.is_active && "Неактивна"}
                      </Badge>
                    </TableCell>
                    <TableCell className="pr-5 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Редактировать ${recordName(record)}`}
                        onClick={() => setEditing(record)}
                      >
                        <Pencil aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        aria-label={`Удалить ${recordName(record)}`}
                        onClick={() => {
                          setDeleting(record)
                          setDeleteError("")
                        }}
                      >
                        <Trash2 aria-hidden="true" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-4 text-sm text-muted-foreground">
          <p aria-live="polite">
            Страница {page + 1}
            {!loading && !error && ` · записей: ${rows.length}`}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={loading || page === 0}
              onClick={() => setPage((value) => value - 1)}
            >
              <ChevronLeft aria-hidden="true" />
              Назад
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={loading || !!error || !hasNext}
              onClick={() => setPage((value) => value + 1)}
            >
              Далее
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
        </div>
      </section>

      {editing !== undefined && (
        <RecordDialog
          resource={resource}
          record={editing}
          onClose={() => setEditing(undefined)}
          onSaved={refresh}
        />
      )}
      <AlertDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) {
            setDeleting(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить запись?</AlertDialogTitle>
            <AlertDialogDescription>
              Запись «{deleting && recordName(deleting)}» будет удалена без возможности
              восстановления. Связанные занятия могут быть удалены вместе с ней.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <ErrorNotice message={deleteError} />}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleteBusy}
              className="bg-destructive hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault()
                void remove()
              }}
            >
              {deleteBusy && "Удаляем"}
              {!deleteBusy && "Удалить"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
