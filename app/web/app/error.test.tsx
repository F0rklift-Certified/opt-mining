import { fireEvent, render, screen } from "@testing-library/react";

import ErrorBoundary from "./error";

describe("App Router error boundary (QA F-14)", () => {
  it("shows a plain alert and retries on request", () => {
    const reset = jest.fn();
    const spy = jest.spyOn(console, "error").mockImplementation(() => undefined);
    render(<ErrorBoundary error={new Error("boom")} reset={reset} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/something went wrong/i);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});
