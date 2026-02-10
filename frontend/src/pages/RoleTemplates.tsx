import { useState, useMemo } from 'react'
import { toast } from 'sonner'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from '@/components/ui/hover-card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAuth } from '@/context/AuthContext'
import {
  getRoleTemplates,
  createRoleTemplate,
  updateRoleTemplate,
  deleteRoleTemplate,
} from '@/api/roles'
import type { RoleTemplateResponse } from '@/api/roles'
import { ApiError } from '@/api/client'
import SearchInput from '@/components/SearchInput'
import TagInput from '@/components/TagInput'

interface TemplateFormState {
  name: string
  description: string
  managed_policy_arns: string[]
}

const emptyForm: TemplateFormState = {
  name: '',
  description: '',
  managed_policy_arns: [],
}

export default function RoleTemplates() {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RoleTemplateResponse | null>(null)
  const [form, setForm] = useState<TemplateFormState>(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [deleteTemplate, setDeleteTemplate] = useState<RoleTemplateResponse | null>(null)

  const { data: templates, isLoading } = useQuery({
    queryKey: ['role-templates'],
    queryFn: getRoleTemplates,
  })

  const filtered = useMemo(() => {
    if (!templates) return []
    const q = search.toLowerCase()
    if (!q) return templates
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description ?? '').toLowerCase().includes(q) ||
        t.managed_policy_arns.some((a) => a.toLowerCase().includes(q))
    )
  }, [templates, search])

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm)
    setError('')
    setDialogOpen(true)
  }

  const openEdit = (template: RoleTemplateResponse) => {
    setEditing(template)
    setForm({
      name: template.name,
      description: template.description ?? '',
      managed_policy_arns: [...template.managed_policy_arns],
    })
    setError('')
    setDialogOpen(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      if (editing) {
        await updateRoleTemplate(editing.id, {
          name: form.name,
          description: form.description || null,
          managed_policy_arns: form.managed_policy_arns,
        })
      } else {
        await createRoleTemplate({
          name: form.name,
          description: form.description || null,
          managed_policy_arns: form.managed_policy_arns,
        })
      }
      queryClient.invalidateQueries({ queryKey: ['role-templates'] })
      toast.success(editing ? 'Template updated' : 'Template created')
      setDialogOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save template')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTemplate) return
    try {
      await deleteRoleTemplate(deleteTemplate.id)
      queryClient.invalidateQueries({ queryKey: ['role-templates'] })
      toast.success('Template deleted')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to delete template')
    } finally {
      setDeleteTemplate(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Role Templates</h1>
        {isAdmin && (
          <Button onClick={openCreate}>+ New Template</Button>
        )}
      </div>

      <SearchInput
        placeholder="Search templates..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <div className="text-muted-foreground">Loading templates...</div>
      ) : !templates?.length ? (
        <div className="text-muted-foreground">No role templates found.</div>
      ) : filtered.length === 0 ? (
        <div className="text-muted-foreground">No templates match your search.</div>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Managed Policies</TableHead>
                {isAdmin && <TableHead className="text-right">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((template) => (
                <TableRow key={template.id}>
                  <TableCell className="font-medium">{template.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {template.description ?? '—'}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {template.managed_policy_arns.length > 0
                        ? template.managed_policy_arns.map((arn) => (
                            <HoverCard key={arn} openDelay={200} closeDelay={0}>
                              <HoverCardTrigger asChild>
                                <Badge variant="outline" className="text-xs font-mono cursor-default">
                                  {arn.split('/').pop()}
                                </Badge>
                              </HoverCardTrigger>
                              <HoverCardContent className="w-auto max-w-sm">
                                <p className="text-xs font-mono break-all">{arn}</p>
                              </HoverCardContent>
                            </HoverCard>
                          ))
                        : '—'}
                    </div>
                  </TableCell>
                  {isAdmin && (
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openEdit(template)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => setDeleteTemplate(template)}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Template' : 'New Template'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="space-y-2">
              <Label htmlFor="template_name">Name</Label>
              <Input
                id="template_name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                maxLength={128}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="template_description">Description</Label>
              <Input
                id="template_description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                maxLength={1000}
              />
            </div>
            <div className="space-y-2">
              <Label>Managed Policy ARNs</Label>
              <TagInput
                value={form.managed_policy_arns}
                onChange={(arns) => setForm({ ...form, managed_policy_arns: arns })}
                placeholder="arn:aws:iam::aws:policy/..."
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Saving...' : editing ? 'Save Changes' : 'Create Template'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTemplate} onOpenChange={(open) => !open && setDeleteTemplate(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete template?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete template "{deleteTemplate?.name}"? This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
