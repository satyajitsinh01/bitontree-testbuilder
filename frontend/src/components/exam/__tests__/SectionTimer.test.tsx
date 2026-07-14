import { act, render, screen } from "@testing-library/react";
import { SectionTimer } from "../SectionTimer";

describe("SectionTimer (UT-M6-02)", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  function iso(date: Date): string {
    return date.toISOString().replace("Z", "");
  }

  it("renders remaining time from the server deadline, not local assumptions", () => {
    const now = new Date();
    const deadline = new Date(now.getTime() + 5 * 60 * 1000);
    render(
      <SectionTimer deadlineAt={iso(deadline)} serverNow={iso(now)} onExpire={() => {}} />
    );
    expect(screen.getByTestId("section-timer")).toHaveTextContent(/0[45]:\d\d/);
  });

  it("corrects for client clock drift using server_now", () => {
    const now = new Date();
    // server says it is 10 minutes EARLIER than the local clock
    const serverNow = new Date(now.getTime() - 10 * 60 * 1000);
    const deadline = new Date(serverNow.getTime() + 3 * 60 * 1000);
    render(
      <SectionTimer
        deadlineAt={iso(deadline)}
        serverNow={iso(serverNow)}
        onExpire={() => {}}
      />
    );
    // without drift correction this would show 00:00 (deadline already past locally)
    expect(screen.getByTestId("section-timer")).toHaveTextContent(/0[23]:\d\d/);
  });

  it("fires onExpire exactly once when the countdown reaches zero", () => {
    const onExpire = jest.fn();
    const now = new Date();
    const deadline = new Date(now.getTime() - 1000); // already past on first tick
    render(
      <SectionTimer deadlineAt={iso(deadline)} serverNow={iso(now)} onExpire={onExpire} />
    );
    act(() => {
      jest.advanceTimersByTime(1100);
    });
    expect(onExpire).toHaveBeenCalledTimes(1);
    act(() => {
      jest.advanceTimersByTime(5000); // interval cleared — no repeat firing
    });
    expect(onExpire).toHaveBeenCalledTimes(1);
  });
});
