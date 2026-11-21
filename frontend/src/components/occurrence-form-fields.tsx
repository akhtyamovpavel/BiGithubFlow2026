import { useId } from "react"
import {
  DAY_NAMES,
  formatRuDate,
  getIsoWeekday,
  getIsoWeekParity,
  isLessonScheduledOnDate,
  parseIsoDate,
} from "@/lib/dates"
import type { Classroom, Lesson, OccurrenceExceptionAction, TimeSlot } from "@/lib/models"
import { cn } from "@/lib/utils"
import { formatTimeSlot } from "@/components/lesson-dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export type ChangeScope = "occurrence" | "series"

export interface OccurrenceFormState {
  scope: ChangeScope
  action: OccurrenceExceptionAction
  occurrenceDate: string
  targetDate: string
  timeSlotId: string
  classroomId: string
  reason: string
}

const fieldCls =
  "flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"

export function dateHint(iso: string): string {
  if (!parseIsoDate(iso)) return ""
  const day = DAY_NAMES[getIsoWeekday(iso) - 1] || ""
  return `${day} · ${getIsoWeekParity(iso) === "ODD_WEEK" ? "Нечётная неделя" : "Чётная неделя"}`
}

export function validateOccurrenceForm(
  lesson: Lesson,
  form: OccurrenceFormState,
  timeSlots: TimeSlot[],
): string {
  if (form.scope === "occurrence") {
    if (!parseIsoDate(form.occurrenceDate)) return "Выбери корректную дату вхождения."
    if (!isLessonScheduledOnDate(lesson, form.occurrenceDate))
      return "В выбранную дату это занятие не проводится. Проверь день недели и чётность."
    if (!form.reason.trim()) return "Укажи причину переноса или отмены."
  }
  if (form.action === "move") {
    if (form.scope === "occurrence") {
      if (!parseIsoDate(form.targetDate)) return "Выбери корректную новую дату."
      const slot = timeSlots.find((s) => String(s.id) === form.timeSlotId)
      if (!slot || slot.day_of_week !== getIsoWeekday(form.targetDate))
        return "Новая дата не совпадает с днём недели выбранного слота."
    }
    if (!form.timeSlotId || !form.classroomId) return "Выбери новый слот и аудиторию."
  }
  return ""
}

export function OccurrenceScopeSelector(props: {
  scope: ChangeScope
  occurrenceDate: string
  canChangeSeries: boolean
  disabled: boolean
  onChange: (scope: ChangeScope) => void
}) {
  const id = useId()
  const items: Array<{ value: ChangeScope; title: string; hint: string; off?: boolean }> = [
    { value: "occurrence", title: "Только одно занятие", hint: "Остальные недели без изменений." },
    {
      value: "series",
      title: "Вся серия занятий",
      hint: "Затронет все недели серии.",
      off: !props.canChangeSeries,
    },
  ]
  return (
    <div className="space-y-2">
      <fieldset disabled={props.disabled} className="grid gap-2 sm:grid-cols-2">
        <legend className="mb-1.5 text-sm font-medium">Область изменения</legend>
        {items.map((item) => (
          <label
            key={item.value}
            className={cn(
              "flex items-start gap-2 rounded-lg border p-2.5 text-xs",
              item.off ? "cursor-not-allowed opacity-60" : "cursor-pointer",
              props.scope === item.value &&
                (item.value === "series"
                  ? "border-amber-500 bg-amber-500/10"
                  : "border-primary bg-primary/5"),
            )}
          >
            <input
              type="radio"
              name={`${id}-scope`}
              disabled={item.off}
              checked={props.scope === item.value}
              onChange={() => props.onChange(item.value)}
              className="mt-0.5 accent-primary"
            />
            <span>
              <strong className="block text-sm">{item.title}</strong>
              {item.hint}
            </span>
          </label>
        ))}
      </fieldset>
      <p role="status" className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
        {props.scope === "occurrence"
          ? `Область: одно занятие (${formatRuDate(props.occurrenceDate)}) — остальные недели без изменений.`
          : "Область: вся серия занятий — изменение затронет каждую неделю."}
      </p>
    </div>
  )
}

export function OccurrenceFormFields(props: {
  lesson: Lesson
  form: OccurrenceFormState
  slots: TimeSlot[]
  rooms: Classroom[]
  busy: boolean
  onPatch: (patch: Partial<OccurrenceFormState>) => void
  onTargetDateChange: (nextDate: string) => void
}) {
  const id = useId()
  const { lesson, form, slots, rooms, busy, onPatch, onTargetDateChange } = props
  return (
    <div className="space-y-3">
      {form.scope === "occurrence" && (
        <div className="space-y-1">
          <Label htmlFor={`${id}-occ-date`}>Дата вхождения *</Label>
          <Input
            id={`${id}-occ-date`}
            type="date"
            disabled={busy || !!lesson.specific_date}
            value={form.occurrenceDate}
            onChange={(e) => onPatch({ occurrenceDate: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">{dateHint(form.occurrenceDate)}</p>
        </div>
      )}
      {form.action === "move" && (
        <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
          {form.scope === "occurrence" && (
            <div className="space-y-1">
              <Label htmlFor={`${id}-target-date`}>Новая дата *</Label>
              <Input
                id={`${id}-target-date`}
                type="date"
                disabled={busy}
                value={form.targetDate}
                onChange={(e) => onTargetDateChange(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{dateHint(form.targetDate)}</p>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor={`${id}-slot`}>Новый временной слот *</Label>
              <select
                id={`${id}-slot`}
                disabled={busy}
                value={form.timeSlotId}
                onChange={(e) => onPatch({ timeSlotId: e.target.value })}
                className={cn(fieldCls, "h-9")}
              >
                {slots.map((s) => (
                  <option key={s.id} value={String(s.id)}>{formatTimeSlot(s)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`${id}-room`}>Новая аудитория *</Label>
              <select
                id={`${id}-room`}
                disabled={busy}
                value={form.classroomId}
                onChange={(e) => onPatch({ classroomId: e.target.value })}
                className={cn(fieldCls, "h-9")}
              >
                {rooms.map((r) => (
                  <option key={r.id} value={String(r.id)}>
                    {r.building} · {r.room_number} ({r.capacity} мест)
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}
      {form.scope === "occurrence" && (
        <div className="space-y-1">
          <Label htmlFor={`${id}-reason`}>Причина изменения *</Label>
          <textarea
            id={`${id}-reason`}
            disabled={busy}
            value={form.reason}
            onChange={(e) => onPatch({ reason: e.target.value })}
            placeholder="Укажи причину переноса или отмены"
            maxLength={2000}
            className={cn(fieldCls, "min-h-20")}
          />
        </div>
      )}
    </div>
  )
}
