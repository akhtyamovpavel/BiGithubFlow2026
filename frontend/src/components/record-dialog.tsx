import { useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { ApiError, errorMessage, groupsApi, teachersApi } from "@/lib/api"
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
  is_active: boolean
}

interface FieldDefinition {
  name: Exclude<keyof FormValues, "is_active">
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
  const isGroup = resource === "groups"
  let fields = teacherFields
  let noun = "преподавателя"
  if (isGroup) {
    fields = groupFields
    noun = "группу"
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
    is_active: true,
  }
  if (record && "name" in record) {
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
  const form = useForm<FormValues>({ defaultValues: initial })
  const [error, setError] = useState("")
  const busy = form.formState.isSubmitting

  async function save(values: FormValues) {
    setError("")
    try {
      if (isGroup) {
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
      } else {
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
          let field: "name" | "email" = "email"
          let message = "Преподаватель с таким email уже существует."
          if (isGroup) {
            field = "name"
            message = "Группа с таким шифром уже существует."
          }
          form.setError(field, { message }, { shouldFocus: true })
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
