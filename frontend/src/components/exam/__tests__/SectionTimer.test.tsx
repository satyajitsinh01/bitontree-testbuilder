import { act, render, screen } from "@testing-library/react";
import { SectionTimer } from "../SectionTimer";

class FakeWebSocket {
  static instance: FakeWebSocket;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instance = this;
  }

  close() {}

  sendMessage(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

describe("SectionTimer server WebSocket", () => {
  beforeEach(() => {
    window.localStorage.setItem("tb_candidate_token", "candidate-token");
    global.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  });

  it("renders only the remaining time pushed by the server", () => {
    render(
      <SectionTimer sessionId="session-1" sectionId="section-1" onStateChange={() => {}} />
    );
    expect(screen.getByTestId("section-timer")).toHaveTextContent("--:--");

    act(() => {
      FakeWebSocket.instance.sendMessage({
        status: "active",
        current_section_id: "section-1",
        remaining_seconds: 125,
      });
    });

    expect(screen.getByTestId("section-timer")).toHaveTextContent("02:05");
  });

  it("refreshes exam state when the server advances or submits", () => {
    const onStateChange = jest.fn();
    render(
      <SectionTimer
        sessionId="session-1"
        sectionId="section-1"
        onStateChange={onStateChange}
      />
    );

    act(() => {
      FakeWebSocket.instance.sendMessage({
        status: "active",
        current_section_id: "section-2",
        remaining_seconds: 600,
      });
    });

    expect(onStateChange).toHaveBeenCalledTimes(1);
  });
});
