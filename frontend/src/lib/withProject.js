/** Attach the selected project to a SharePoint (or similar) create payload. */
export function withProject(form, projectId) {
  return { ...form, project_id: form.project_id || projectId || null }
}
