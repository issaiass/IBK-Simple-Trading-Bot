/** Where a section starts, measured from the top of the viewport. */
export interface SectionPosition {
  id: string;
  top: number;
}

/** A section becomes current once its top passes this fraction of the viewport height. */
const READING_LINE = 0.3;

/**
 * Which section the reader is on: the last one whose top has passed the reading line. At the very
 * bottom of the page the last section wins, since a short final section may never reach the line.
 */
export function pickActiveSection(
  sections: SectionPosition[],
  viewportHeight: number,
  atBottom: boolean,
): string | undefined {
  if (sections.length === 0) return undefined;
  if (atBottom) return sections[sections.length - 1].id;

  let active = sections[0].id;
  for (const section of sections) {
    if (section.top <= viewportHeight * READING_LINE) active = section.id;
  }
  return active;
}
