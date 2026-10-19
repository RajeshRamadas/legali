import type { LawyerCard } from "@homexo/shared";

export default function Rating({ lawyer }: { lawyer: Pick<LawyerCard, "rating" | "review_count"> }) {
  if (lawyer.rating === null) return <span className="lw-rating"><small>New on Homexo</small></span>;
  return <span className="lw-rating"><span className="lw-star">★ {lawyer.rating.toFixed(1)}</span><small>{lawyer.review_count} review{lawyer.review_count === 1 ? "" : "s"}</small></span>;
}
