import { categoryLabel, t } from "@/lib/i18n/th";
import type { Category } from "@/types";

export default function CategorySelector({ categories, selected, onChange, disabled }: { categories: Category[]; selected: string[]; onChange: (codes: string[]) => void; disabled?: boolean }) {
  return <div className="category-pills" aria-label={t("Content categories")}>{categories.map(category => <button key={category.code} className={`category-pill ${selected.includes(category.code) ? "selected" : ""}`} aria-pressed={selected.includes(category.code)} disabled={disabled} onClick={() => onChange(selected.includes(category.code) ? selected.filter(code => code !== category.code) : [...selected, category.code])}>{categoryLabel(category)}</button>)}</div>;
}
