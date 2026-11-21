import { COURIER_STATUS_LABELS, type CourierShipment } from "@homexo/shared";

const dateFormat = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short",
});

export default function CourierTracking({ shipment }: { shipment: CourierShipment | null | undefined }) {
  if (shipment === undefined) return null;
  return (
    <section className="dc-card" aria-label="Courier tracking">
      <h3>Courier tracking</h3>
      {shipment === null ? <p>No dispatch has been recorded yet.</p> : (
        <>
          <p><strong>{COURIER_STATUS_LABELS[shipment.status]}</strong> · {shipment.carrier}</p>
          <p style={{ overflowWrap: "anywhere" }}>Tracking number <strong>{shipment.tracking_number}</strong></p>
          <p className="dc-muted">
            Updated by your case team on {dateFormat.format(new Date(shipment.updated_at))}.
          </p>
          {shipment.history.length > 1 && (
            <details>
              <summary>Delivery history</summary>
              <ol className="ticket-timeline">
                {[...shipment.history].reverse().map((event) => (
                  <li key={event.at + "-" + event.status}>
                    <b>{COURIER_STATUS_LABELS[event.status]}</b>
                    <small>{dateFormat.format(new Date(event.at))}</small>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </>
      )}
    </section>
  );
}
