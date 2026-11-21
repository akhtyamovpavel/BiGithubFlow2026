import { ShieldAlert } from "lucide-react"
import { Link, Navigate, Outlet, useLocation } from "react-router-dom"
import { ROLE_LABELS, useAuth } from "@/lib/auth"
import { ErrorNotice, LoadingRows } from "@/components/feedback"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export function RequireAuth() {
  const { status, bootError, retryBootstrap, logout } = useAuth()
  const location = useLocation()

  if (status === "loading") {
    return (
      <div className="mx-auto max-w-2xl py-16">
        <LoadingRows />
      </div>
    )
  }

  if (status === "error") {
    return (
      <div className="mx-auto max-w-lg space-y-4 px-4 py-16">
        <ErrorNotice message={bootError} retry={retryBootstrap} />
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => void logout()}>
            Перейти ко входу
          </Button>
        </div>
      </div>
    )
  }

  if (status !== "authenticated") {
    const from = `${location.pathname}${location.search}`
    return <Navigate to="/login" replace state={{ from }} />
  }

  return <Outlet />
}

export function AccessDenied({ section }: { section: string }) {
  const { user } = useAuth()
  return (
    <div
      role="alert"
      className="mx-auto max-w-xl space-y-5 rounded-xl border border-destructive/25 bg-card p-8"
    >
      <div className="flex items-center gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
          <ShieldAlert className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <Badge variant="outline" className="border-destructive/30 text-destructive">
            Ошибка 403
          </Badge>
          <h1 className="text-xl font-semibold tracking-tight">Доступ запрещён</h1>
        </div>
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">
        Недостаточно прав для доступа к разделу «{section}». Этот раздел доступен только
        администратору.
        {user && ` Твоя текущая роль: ${ROLE_LABELS[user.role]}.`}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link to="/schedule">Вернуться к расписанию</Link>
        </Button>
      </div>
    </div>
  )
}
