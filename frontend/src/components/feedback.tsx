import { AlertCircle, Inbox } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/25 bg-destructive/5 p-4 text-sm"
    >
      <AlertCircle className="size-5 shrink-0 text-destructive" aria-hidden="true" />
      <p className="min-w-0 flex-1">{message}</p>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  )
}

export function LoadingRows() {
  return (
    <div role="status" className="space-y-4 p-6">
      <span className="sr-only">Загрузка данных</span>
      {Array.from({ length: 5 }, (_, index) => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center" role="status">
      <Inbox className="size-8 text-muted-foreground" aria-hidden="true" />
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
