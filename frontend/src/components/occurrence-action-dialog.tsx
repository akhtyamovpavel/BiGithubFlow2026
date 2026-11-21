import { useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { errorMessage, lessonExceptionsApi, lessonsApi } from "@/lib/api"
import { formatRuDate, getIsoWeekday, parseIsoDate } from "@/lib/dates"
import type { Classroom, Lesson, OccurrenceExceptionAction, TimeSlot } from "@/lib/models"
import { ErrorNotice } from "@/components/feedback"
import { formatTimeSlot } from "@/components/lesson-dialog"
import {
  OccurrenceFormFields,
  OccurrenceScopeSelector,
  validateOccurrenceForm,
  type OccurrenceFormState,
} from "@/components/occurrence-form-fields"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

async function submitOccurrenceChange(lesson: Lesson, form: OccurrenceFormState): Promise<string> {
  if (form.scope === "occurrence") {
    const payload =
      form.action === "cancel"
        ? { occurrence_date: form.occurrenceDate, action: "cancel" as const, reason: form.reason.trim() }
        : {
            occurrence_date: form.occurrenceDate,
            action: "move" as const,
            reason: form.reason.trim(),
            target_date: form.targetDate,
            time_slot_id: Number(form.timeSlotId),
            classroom_id: Number(form.classroomId),
          }
    await lessonExceptionsApi.create(lesson.id, payload)
    return form.action === "move"
      ? `Занятие перенесено на ${formatRuDate(form.targetDate)}`
      : `Занятие на ${formatRuDate(form.occurrenceDate)} отменено`
  }
  if (form.action === "cancel") {
    await lessonsApi.remove(lesson.id)
    return "Серия занятий удалена"
  }
  await lessonsApi.save(
    {
      subject_id: lesson.subject_id,
      teacher_id: lesson.teacher_id,
      group_id: lesson.group_id,
      classroom_id: Number(form.classroomId),
      time_slot_id: Number(form.timeSlotId),
      lesson_type: lesson.lesson_type,
      parity: lesson.parity,
      specific_date: lesson.specific_date,
    },
    lesson.id,
  )
  return "Серия занятий обновлена"
}

export function OccurrenceActionDialog(props: {
  lesson: Lesson
  initialAction: OccurrenceExceptionAction
  initialDate: string
  classrooms: Classroom[]
  timeSlots: TimeSlot[]
  onClose: () => void
  onSaved: () => void
}) {
  const { lesson, initialAction, initialDate, classrooms, timeSlots, onClose, onSaved } = props
  const lockRef = useRef(false)
  const canChangeSeries = !lesson.specific_date && (lesson.exceptions?.length ?? 0) === 0
  const rooms = useMemo(() => {
    const active = classrooms.filter((r) => r.is_active || r.id === lesson.classroom_id)
    return active.length > 0 ? active : classrooms
  }, [classrooms, lesson.classroom_id])

  const [form, setForm] = useState<OccurrenceFormState>({
    scope: "occurrence",
    action: initialAction,
    occurrenceDate: initialDate,
    targetDate: initialDate,
    timeSlotId: String(lesson.time_slot_id),
    classroomId: String(lesson.classroom_id),
    reason: "",
  })
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const slots = useMemo(() => {
    if (form.scope === "series" || !parseIsoDate(form.targetDate)) return timeSlots
    const matching = timeSlots.filter((s) => s.day_of_week === getIsoWeekday(form.targetDate))
    return matching.length > 0 ? matching : timeSlots
  }, [form.scope, form.targetDate, timeSlots])

  function patchForm(patch: Partial<OccurrenceFormState>) {
    setForm((prev) => ({ ...prev, ...patch }))
    setError("")
  }

  function handleTargetDateChange(next: string) {
    let nextSlotId = form.timeSlotId
    if (parseIsoDate(next)) {
      const daySlots = timeSlots.filter((s) => s.day_of_week === getIsoWeekday(next))
      if (daySlots.length > 0 && !daySlots.some((s) => String(s.id) === nextSlotId)) {
        const sameNum = daySlots.find((s) => s.slot_number === lesson.time_slot?.slot_number)
        nextSlotId = String(sameNum?.id ?? daySlots[0].id)
      }
    }
    patchForm({ targetDate: next, timeSlotId: nextSlotId })
  }

  async function handleConfirm() {
    if (lockRef.current) return
    lockRef.current = true
    setBusy(true)
    setError("")
    try {
      toast.success(await submitOccurrenceChange(lesson, form))
      onSaved()
      onClose()
    } catch (failure) {
      lockRef.current = false
      const msg = errorMessage(failure)
      setError(msg)
      setConfirming(false)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const slotLabel = slots.find((s) => String(s.id) === form.timeSlotId)
  const roomLabel = rooms.find((r) => String(r.id) === form.classroomId)
  const isCancel = form.action === "cancel"

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-lg"
        onInteractOutside={(e) => busy && e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{isCancel ? "Отменить занятие" : "Перенести занятие"}</DialogTitle>
          <DialogDescription>
            {lesson.subject?.name || `Дисциплина #${lesson.subject_id}`} ·{" "}
            {lesson.group?.name || `Группа #${lesson.group_id}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-1">
            {(["move", "cancel"] as const).map((mode) => (
              <Button
                key={mode}
                type="button"
                size="sm"
                variant={form.action === mode ? (mode === "cancel" ? "destructive" : "default") : "ghost"}
                disabled={busy}
                onClick={() => {
                  setConfirming(false)
                  patchForm({ action: mode })
                }}
              >
                {mode === "move" ? "Перенести" : "Отменить"}
              </Button>
            ))}
          </div>

          <OccurrenceScopeSelector
            scope={form.scope}
            occurrenceDate={form.occurrenceDate}
            canChangeSeries={canChangeSeries}
            disabled={busy || confirming}
            onChange={(scope) => patchForm({ scope })}
          />

          {!confirming ? (
            <form
              className="space-y-4"
              noValidate
              onSubmit={(e) => {
                e.preventDefault()
                const msg = validateOccurrenceForm(lesson, form, timeSlots)
                if (msg) setError(msg)
                else {
                  setError("")
                  setConfirming(true)
                }
              }}
            >
              <OccurrenceFormFields
                lesson={lesson}
                form={form}
                slots={slots}
                rooms={rooms}
                busy={busy}
                onPatch={patchForm}
                onTargetDateChange={handleTargetDateChange}
              />
              {error && <ErrorNotice message={error} />}
              <DialogFooter>
                <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
                  Закрыть
                </Button>
                <Button type="submit" variant={isCancel ? "destructive" : "default"}>
                  Продолжить
                </Button>
              </DialogFooter>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="space-y-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                <p className="font-semibold">Подтверди операцию</p>
                <p>
                  Действие: {isCancel ? "отмена" : "перенос"} (
                  {form.scope === "occurrence"
                    ? `одно занятие ${formatRuDate(form.occurrenceDate)}`
                    : "вся серия"}
                  ).
                </p>
                {!isCancel && slotLabel && roomLabel && (
                  <p>
                    Назначение: {form.scope === "occurrence" ? `${formatRuDate(form.targetDate)}, ` : ""}
                    {formatTimeSlot(slotLabel)}, {roomLabel.building} · {roomLabel.room_number}.
                  </p>
                )}
                {form.scope === "occurrence" && <p>Причина: {form.reason.trim()}</p>}
              </div>
              {error && <ErrorNotice message={error} />}
              <DialogFooter>
                <Button type="button" variant="outline" disabled={busy} onClick={() => setConfirming(false)}>
                  Назад
                </Button>
                <Button
                  type="button"
                  variant={isCancel ? "destructive" : "default"}
                  disabled={busy}
                  onClick={() => void handleConfirm()}
                >
                  {busy ? "Сохраняем..." : isCancel ? "Подтвердить отмену" : "Подтвердить перенос"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
