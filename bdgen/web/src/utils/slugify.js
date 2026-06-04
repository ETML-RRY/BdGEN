/**
 * Mirrors the Python _slugify() in bdgen/service/lifecycle.py:
 *   - NFD normalize (strips diacritics via \p{M} combining marks)
 *   - lowercase
 *   - replace any run of non-[a-z0-9] with a single underscore
 *   - strip leading/trailing underscores
 *   - cap at 60 chars
 */
export function slugify(text) {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
}

/**
 * Returns true if the string is already a valid slug (or empty).
 * Valid slug: only lowercase letters, digits, underscores; must start and end
 * with a letter or digit.
 */
export function isValidSlug(text) {
  return text === "" || /^[a-z0-9]([a-z0-9_]*[a-z0-9])?$/.test(text);
}

/**
 * Light sanitizer for the slug input field.
 * Keeps underscores as-is (so the user can type them), only strips characters
 * that are truly invalid. The full slugify() (with stripping and collapsing) is
 * applied by the backend on submit.
 */
export function sanitizeSlugInput(text) {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "")
    .slice(0, 60);
}
