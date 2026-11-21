import { useEffect, useId, useState } from "react"
import { Lock, Plus, ShieldCheck, Unlock, UserRound } from "lucide-react"
import { toast } from "sonner"
import { ApiError, errorMessage, usersApi } from "@/lib/api"
import { ROLE_LABELS, useAuth } from "@/lib/auth"
import type { User, UserRole } from "@/lib/models"
import { cn } from "@/lib/utils"
import { AccessDenied } from "@/components/auth-guard"
import { EmptyState, ErrorNotice, LoadingRows } from "@/components/feedback"
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
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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

const ROLES: UserRole[] = ["reader", "dispatcher", "admin"]

const selectClassName =
  "flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"

function CreateUserDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const baseId = useId()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole] = useState<UserRole>("reader")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanedUsername = username.trim()
    if (!cleanedUsername || cleanedUsername.length > 100 || /\s/.test(cleanedUsername)) {
      setError("Логин должен содержать от 1 до 100 символов без пробелов.")
      return
    }
    if (password.length < 8 || password.length > 128) {
      setError("Пароль должен содержать от 8 до 128 символов.")
      return
    }
    setBusy(true)
    setError("")
    try {
      await usersApi.create({ username: cleanedUsername, password, role })
      toast.success(`Пользователь «${cleanedUsername}» создан`)
      onCreated()
      onClose()
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 422 && failure.fields.password) {
        setError("Пароль должен содержать от 8 до 128 символов.")
      } else {
        setError(errorMessage(failure))
      }
    } finally {
      setBusy(false)
    }
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
        className="sm:max-w-md"
        onInteractOutside={(event) => {
          if (busy) {
            event.preventDefault()
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Создать пользователя</DialogTitle>
          <DialogDescription>
            Укажи логин, начальный пароль (от 8 символов) и роль доступа.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <fieldset disabled={busy} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`${baseId}-username`}>Логин *</Label>
              <Input
                id={`${baseId}-username`}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="off"
                placeholder="Например, dispatcher_ivan"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${baseId}-password`}>Пароль *</Label>
              <Input
                id={`${baseId}-password`}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="Минимум 8 символов"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${baseId}-role`}>Роль *</Label>
              <select
                id={`${baseId}-role`}
                value={role}
                onChange={(event) => setRole(event.target.value as UserRole)}
                className={cn(selectClassName, "w-full")}
              >
                {ROLES.map((item) => (
                  <option key={item} value={item}>
                    {ROLE_LABELS[item]}
                  </option>
                ))}
              </select>
            </div>
          </fieldset>

          {error && <ErrorNotice message={error} />}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Создаём..." : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function UsersPage() {
  const { user: currentUser, isAdmin } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  const [creating, setCreating] = useState(false)
  const [busyUserId, setBusyUserId] = useState<number | null>(null)
  const [blockingUser, setBlockingUser] = useState<User | null>(null)
  const [blockError, setBlockError] = useState("")

  useEffect(() => {
    if (!isAdmin) {
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError("")
    usersApi
      .list(controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) {
          setUsers(records)
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setUsers([])
          setError(errorMessage(failure))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [isAdmin, revision])

  if (!isAdmin) {
    return <AccessDenied section="Пользователи" />
  }

  function refresh() {
    setRevision((value) => value + 1)
  }

  async function handleRoleChange(target: User, nextRole: UserRole) {
    if (target.role === nextRole) {
      return
    }
    setBusyUserId(target.id)
    try {
      const updated = await usersApi.update(target.id, { role: nextRole })
      setUsers((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      toast.success(`Роль «${target.username}» изменена: ${ROLE_LABELS[nextRole]}`)
    } catch (failure) {
      toast.error(errorMessage(failure))
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleToggleActive(target: User, nextActive: boolean) {
    setBusyUserId(target.id)
    setBlockError("")
    try {
      const updated = await usersApi.update(target.id, { is_active: nextActive })
      setUsers((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      setBlockingUser(null)
      toast.success(
        nextActive
          ? `Аккаунт «${target.username}» разблокирован`
          : `Аккаунт «${target.username}» заблокирован`,
      )
    } catch (failure) {
      const message = errorMessage(failure)
      if (!nextActive) {
        setBlockError(message)
      }
      toast.error(message)
    } finally {
      setBusyUserId(null)
    }
  }

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-sm font-medium text-primary">Администрирование</p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Пользователи</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Управление учётными записями, правами доступа и блокировкой. Смена роли и блокировка
            аккаунта вступают в силу немедленно.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus aria-hidden="true" />
          Создать пользователя
        </Button>
      </div>

      <section className="overflow-hidden rounded-xl border bg-card" aria-label="Пользователи">
        {loading && <LoadingRows />}
        {!loading && error && (
          <div className="p-5">
            <ErrorNotice message={error} retry={refresh} />
          </div>
        )}
        {!loading && !error && users.length === 0 && (
          <EmptyState
            title="Пользователей пока нет"
            description="Создай первую учётную запись для работы с системой."
          />
        )}
        {!loading && !error && users.length > 0 && (
          <div className="overflow-x-auto">
            <Table className="min-w-[680px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Пользователь</TableHead>
                  <TableHead>Роль</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="pr-5 text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((record) => {
                  const isSelf = currentUser?.id === record.id
                  const rowBusy = busyUserId === record.id
                  return (
                    <TableRow key={record.id}>
                      <TableCell className="py-4 pl-5">
                        <div className="flex items-center gap-3">
                          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/7 text-primary">
                            {record.role === "admin" ? (
                              <ShieldCheck className="size-4" aria-hidden="true" />
                            ) : (
                              <UserRound className="size-4" aria-hidden="true" />
                            )}
                          </span>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{record.username}</span>
                            {isSelf && (
                              <Badge variant="outline" className="text-xs font-normal">
                                Вы
                              </Badge>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <select
                          aria-label={`Роль пользователя ${record.username}`}
                          value={record.role}
                          disabled={rowBusy || isSelf}
                          onChange={(event) =>
                            void handleRoleChange(record, event.target.value as UserRole)
                          }
                          className={selectClassName}
                        >
                          {ROLES.map((item) => (
                            <option key={item} value={item}>
                              {ROLE_LABELS[item]}
                            </option>
                          ))}
                        </select>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className={cn(
                            record.is_active
                              ? "bg-primary/10 text-primary"
                              : "bg-destructive/10 text-destructive",
                          )}
                        >
                          {record.is_active ? "Активен" : "Заблокирован"}
                        </Badge>
                      </TableCell>
                      <TableCell className="pr-5 text-right">
                        {isSelf ? (
                          <span className="text-xs text-muted-foreground">Текущая сессия</span>
                        ) : record.is_active ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={rowBusy}
                            className="text-destructive hover:text-destructive"
                            aria-label={`Заблокировать ${record.username}`}
                            onClick={() => {
                              setBlockingUser(record)
                              setBlockError("")
                            }}
                          >
                            <Lock className="size-3.5" aria-hidden="true" />
                            Заблокировать
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={rowBusy}
                            aria-label={`Разблокировать ${record.username}`}
                            onClick={() => void handleToggleActive(record, true)}
                          >
                            <Unlock className="size-3.5" aria-hidden="true" />
                            Разблокировать
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {creating && (
        <CreateUserDialog onClose={() => setCreating(false)} onCreated={refresh} />
      )}

      <AlertDialog
        open={!!blockingUser}
        onOpenChange={(open) => {
          if (!open && busyUserId === null) {
            setBlockingUser(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Заблокировать пользователя?</AlertDialogTitle>
            <AlertDialogDescription>
              Аккаунт «{blockingUser?.username}» будет заблокирован, а все его активные сессии
              немедленно отозваны.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {blockError && <ErrorNotice message={blockError} />}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busyUserId !== null}>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={busyUserId !== null}
              className="bg-destructive hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault()
                if (blockingUser) {
                  void handleToggleActive(blockingUser, false)
                }
              }}
            >
              {busyUserId !== null ? "Блокируем..." : "Заблокировать"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
