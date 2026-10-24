import { useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import {
  ApiError,
  classroomsApi,
  errorMessage,
  groupsApi,
  subjectsApi,
  teachersApi,
} from "@/lib/api"
import type { DirectoryRecord, Resource } from "@/lib/models"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { ErrorNotice } from "@/components/feedback"

interface FormValues {
  name: string
  faculty: string
  course_number: string
  student_count: string
  full_name: string
  email: string
  department: string
  position: string
  building: string
  room_number: string
  capacity: string
  has_projector: boolean
  has_computers: boolean
  code: string
  description: string
  is_active: boolean
}

type TextFieldName = Exclude<
  keyof FormValues,
  "is_active" | "has_projector" | "has_computers"
>

interface FieldDefinition {
  name: TextFieldName
  label: string
  required?: boolean
  maxLength?: number
  min?: number
  max?: number
  type?: "text" | "email" | "number"
  pattern?: { value: RegExp; message: string }
}

const groupFields: FieldDefinition[] = [
  { name: "name", label: "Шифр группы", required: true, maxLength: 64 },
  { name: "faculty", label: "Факультет", required: true, maxLength: 128 },
  { name: "course_number", label: "Курс", required: true, min: 1, max: 6, type: "number" },
  { name: "student_count", label: "Количество студентов", required: true, min: 1, type: "number" },
]

const teacherFields: FieldDefinition[] = [
  {
    name: "full_name",
    label: "ФИО",
    required: true,
    maxLength: 255,
    pattern: {
      value: /^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s.'-]*$/,
      message: "Используем буквы, пробелы, дефисы, точки и апострофы.",
    },
  },
  {
    name: "email",
    label: "Email",
    required: true,
    maxLength: 255,
    type: "email",
    pattern: {
      value: /^[^@\s]+@[^@\s]+\.[^@\s]+$/,
      message: "Введи email в формате name@example.ru.",
    },
  },
  { name: "department", label: "Кафедра", required: true, maxLength: 128 },
  { name: "position", label: "Должность", maxLength: 128 },
]

const classroomFields: FieldDefinition[] = [
  { name: "building", label: "Корпус", required: true, maxLength: 128 },
  { name: "room_number", label: "Номер аудитории", required: true, maxLength: 64 },
  { name: "capacity", label: "Вместимость", required: true, min: 1, type: "number" },
]

const subjectFields: FieldDefinition[] = [
  { name: "name", label: "Название предмета", required: true, maxLength: 255 },
  { name: "code", label: "Код дисциплины", maxLength: 64 },
  { name: "description", label: "Описание", maxLength: 2000 },
]

export function RecordDialog({
  resource,
  record,
  onClose,
  onSaved,
}: {
  resource: Resource
  record: DirectoryRecord | null
  onClose: () => void
  onSaved: () => void
}) {
  let fields = teacherFields
  let noun = "преподавателя"
  if (resource === "groups") {
    fields = groupFields
    noun = "группу"
  } else if (resource === "classrooms") {
    fields = classroomFields
    noun = "аудиторию"
  } else if (resource === "subjects") {
    fields = subjectFields
    noun = "предмет"
  }

  const initial: FormValues = {
    name: "",
    faculty: "",
    course_number: "1",
    student_count: "1",
    full_name: "",
    email: "",
    department: "",
    position: "",
    building: "",
    room_number: "",
    capacity: "30",
    has_projector: false,
    has_computers: false,
    code: "",
    description: "",
    is_active: true,
  }
  if (record && "faculty" in record) {
    initial.name = record.name
    initial.faculty = record.faculty
    initial.course_number = String(record.course_number)
    initial.student_count = String(record.student_count)
    initial.is_active = record.is_active
  }
  if (record && "full_name" in record) {
    initial.full_name = record.full_name
    initial.email = record.email
    initial.department = record.department
    initial.position = record.position || ""
    initial.is_active = record.is_active
  }
  if (record && "building" in record) {
    initial.building = record.building
    initial.room_number = record.room_number
    initial.capacity = String(record.capacity)
    initial.has_projector = record.has_projector
    initial.has_computers = record.has_computers
    initial.is_active = record.is_active
  }
  if (record && "description" in record) {
    initial.name = record.name
    initial.code = record.code || ""
    initial.description = record.description || ""
  }

  const form = useForm<FormValues>({ defaultValues: initial })
  const [error, setError] = useState("")
  const busy = form.formState.isSubmitting

  async function save(values: FormValues) {
    setError("")
    try {
      if (resource === "groups") {
        await groupsApi.save(
          {
            name: values.name.trim(),
            faculty: values.faculty.trim(),
            course_number: Number(values.course_number),
            student_count: Number(values.student_count),
            is_active: values.is_active,
          },
          record?.id,
        )
      } else if (resource === "teachers") {
        await teachersApi.save(
          {
            full_name: values.full_name.trim().replace(/\s+/g, " "),
            email: values.email.trim().toLowerCase(),
            department: values.department.trim(),
            position: values.position.trim() || null,
            is_active: values.is_active,
          },
          record?.id,
        )
      } else if (resource === "classrooms") {
        await classroomsApi.save(
          {
            building: values.building.trim(),
            room_number: values.room_number.trim(),
            capacity: Number(values.capacity),
            has_projector: values.has_projector,
            has_computers: values.has_computers,
            is_active: values.is_active,
          },
          record?.id,
        )
      } else {
        await subjectsApi.save(
          {
            name: values.name.trim(),
            code: values.code.trim() || null,
            description: values.description.trim(),
          },
          record?.id,
        )
      }
      toast.success("Изменения сохранены")
      onSaved()
      onClose()
    } catch (failure) {
      const message = errorMessage(failure)
      setError(message)
      if (failure instanceof ApiError) {
        for (const field of fields) {
          const fieldError = failure.fields[field.name]
          if (fieldError) {
            form.setError(field.name, { message: fieldError }, { shouldFocus: true })
          }
        }
        if (failure.status === 409) {
          if (resource === "groups") {
            form.setError(
              "name",
              { message: "Группа с таким шифром уже существует." },
              { shouldFocus: true },
            )
          } else if (resource === "teachers") {
            form.setError(
              "email",
              { message: "Преподаватель с таким email уже существует." },
              { shouldFocus: true },
            )
          } else if (resource === "classrooms") {
            form.setError(
              "room_number",
              { message: "Аудитория с таким номером в этом корпусе уже существует." },
              { shouldFocus: true },
            )
          } else {
            form.setError(
              "name",
              { message: "Предмет с таким названием или кодом уже существует." },
              { shouldFocus: true },
            )
          }
        }
      }
    }
  }

  let action = "Добавить"
  if (record) {
    action = "Редактировать"
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose()
        }
      }}
    >
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-lg"
        onInteractOutside={(event) => {
          if (busy) {
            event.preventDefault()
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>
            {action} {noun}
          </DialogTitle>
          <DialogDescription>Обязательные поля отмечены звёздочкой.</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(save)} className="space-y-5" noValidate>
            <fieldset disabled={busy} className="space-y-4">
              {fields.map((definition) => (
                <FormField
                  key={definition.name}
                  control={form.control}
                  name={definition.name}
                  rules={{
                    validate: (value) => {
                      const cleaned = value.trim()
                      if (definition.required && !cleaned) {
                        return "Заполни поле."
                      }
                      if (definition.type === "number") {
                        const number = Number(cleaned)
                        if (!Number.isInteger(number)) {
                          return "Введи целое число."
                        }
                        if (definition.min !== undefined && number < definition.min) {
                          return `Минимальное значение: ${definition.min}.`
                        }
                        if (definition.max !== undefined && number > definition.max) {
                          return `Максимальное значение: ${definition.max}.`
                        }
                      }
                      if (definition.maxLength && cleaned.length > definition.maxLength) {
                        return `Допустимо не более ${definition.maxLength} символов.`
                      }
                      if (definition.pattern && !definition.pattern.value.test(cleaned)) {
                        return definition.pattern.message
                      }
                      return true
                    },
                  }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        {definition.label}
                        {definition.required && " *"}
                      </FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          type={definition.type || "text"}
                          min={definition.min}
                          max={definition.max}
                          step={1}
                          maxLength={definition.maxLength}
                          autoComplete="off"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ))}
              {resource === "classrooms" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="has_projector"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-3 rounded-md border p-3">
                        <FormControl>
                          <input
                            type="checkbox"
                            checked={field.value}
                            onChange={field.onChange}
                            ref={field.ref}
                            name={field.name}
                            onBlur={field.onBlur}
                            className="size-4 accent-primary"
                          />
                        </FormControl>
                        <FormLabel>Проектор</FormLabel>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="has_computers"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-3 rounded-md border p-3">
                        <FormControl>
                          <input
                            type="checkbox"
                            checked={field.value}
                            onChange={field.onChange}
                            ref={field.ref}
                            name={field.name}
                            onBlur={field.onBlur}
                            className="size-4 accent-primary"
                          />
                        </FormControl>
                        <FormLabel>Компьютеры</FormLabel>
                      </FormItem>
                    )}
                  />
                </div>
              )}
              {resource !== "subjects" && (
                <FormField
                  control={form.control}
                  name="is_active"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-3 rounded-md border p-3">
                      <FormControl>
                        <input
                          type="checkbox"
                          checked={field.value}
                          onChange={field.onChange}
                          ref={field.ref}
                          name={field.name}
                          onBlur={field.onBlur}
                          className="size-4 accent-primary"
                        />
                      </FormControl>
                      <FormLabel>Активная запись</FormLabel>
                    </FormItem>
                  )}
                />
              )}
            </fieldset>
            {error && <ErrorNotice message={error} />}
            <DialogFooter>
              <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
                Отмена
              </Button>
              <Button type="submit" disabled={busy}>
                {busy && "Сохраняем"}
                {!busy && "Сохранить"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
