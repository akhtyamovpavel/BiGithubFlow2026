import { lazy, StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom"
import { AppLayout } from "@/components/app-layout"
import { Toaster } from "@/components/ui/sonner"
import { Button } from "@/components/ui/button"
import { LoadingRows } from "@/components/feedback"
import "@/index.css"

const DirectoryPage = lazy(() =>
  import("@/pages/directory-page").then((module) => ({ default: module.DirectoryPage })),
)
const SchedulePage = lazy(() =>
  import("@/pages/schedule-page").then((module) => ({ default: module.SchedulePage })),
)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Suspense fallback={<LoadingRows />}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/schedule" replace />} />
            <Route path="schedule" element={<SchedulePage />} />
            <Route path="groups" element={<DirectoryPage key="groups" resource="groups" />} />
            <Route path="teachers" element={<DirectoryPage key="teachers" resource="teachers" />} />
            <Route
              path="classrooms"
              element={<DirectoryPage key="classrooms" resource="classrooms" />}
            />
            <Route path="subjects" element={<DirectoryPage key="subjects" resource="subjects" />} />
            <Route
              path="*"
              element={
                <div className="space-y-4">
                  <h1 className="text-2xl font-semibold">Страница не найдена</h1>
                  <Button asChild>
                    <Link to="/schedule">Открыть расписание</Link>
                  </Button>
                </div>
              }
            />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
    <Toaster theme="light" position="bottom-right" richColors closeButton />
  </StrictMode>,
)
