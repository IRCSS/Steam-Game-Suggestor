import { useState } from "react";
import { addTag, displayTags, removeTag } from "../lib/filters";

interface Props {
  tags: string[];
  value: string;
  onChange: (value: string) => void;
}

/** Legacy "Must include tags": free-form input, selected chips and the browsable tag catalog. */
export function TagPicker({ tags, value, onChange }: Props) {
  const [search, setSearch] = useState("");
  const chosen = displayTags(value);
  const chosenLower = new Set(chosen.map((t) => t.toLocaleLowerCase()));
  const query = search.trim().toLocaleLowerCase();

  return (
    <section className="filter-group">
      <label className="filter-label" htmlFor="includeTags">
        Must include tags
      </label>
      <input
        id="includeTags"
        type="text"
        placeholder="e.g. Colony Sim, Roguelike"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div id="selectedTags" className="selected-tags">
        {chosen.map((tag) => (
          <span className="selected-tag" key={tag.toLocaleLowerCase()}>
            {tag}
            <button
              type="button"
              aria-label={`Remove tag ${tag}`}
              onClick={() => onChange(removeTag(value, tag))}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <details className="tag-browser">
        <summary>Browse all {tags.length} tags</summary>
        <input
          id="tagSearch"
          type="text"
          placeholder="Search available tags"
          aria-label="Search available tags"
          style={{ marginTop: 10 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div id="availableTagList" className="available-tag-list">
          {tags.map((tag) => (
            <button
              key={tag}
              className={`available-tag${chosenLower.has(tag.toLocaleLowerCase()) ? " selected" : ""}`}
              type="button"
              data-tag={tag}
              hidden={query !== "" && !tag.toLocaleLowerCase().includes(query)}
              onClick={() => onChange(addTag(value, tag))}
            >
              {tag}
            </button>
          ))}
        </div>
      </details>
    </section>
  );
}
