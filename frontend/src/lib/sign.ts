/**
 * Colour by sign, driven by a `data-sign` attribute (see `signOf`). Components state the
 * meaning (positive / negative) and this one class list decides how it looks.
 */
export const signText =
  "data-[sign=positive]:text-emerald-400 data-[sign=negative]:text-rose-400 " +
  "data-[sign=zero]:text-zinc-300 data-[sign=unknown]:text-zinc-500";
