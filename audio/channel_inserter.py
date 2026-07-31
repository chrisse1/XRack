"""
Kanal-Einfügung für die Wiedergabe.
"""


class ChannelInserter:
    """
    Bettet einen interleaved PCM-Datenstrom mit `input_channels`
    Kanälen pro Frame in einen Datenstrom mit `output_channels`
    Kanälen pro Frame ein. Die Eingabe-Kanäle landen ab `start_channel`
    (0-basiert) in der Ausgabe, alle übrigen Kanäle bleiben stumm (0).

    Wird für zwei Zwecke gebraucht:
    - Soundcheck: Eine Aufnahme, die z.B. mit 8 Kanälen aufgenommen
      wurde, landet wieder auf genau denselben (ersten 8) Kanälen des
      Interfaces (start_channel=0).
    - Musikspieler: Eine Musikdatei (z.B. Stereo) soll auf beliebigen
      Kanälen ausgegeben werden können, z.B. Kanal 17+18
      (start_channel=16).

    Das Interface muss dabei immer mit seiner vollen, festen
    Kanalzahl betrieben werden, siehe AudioPlaybackBackend.
    """

    BYTES_PER_SAMPLE = 4

    def __init__(
        self,
        input_channels: int,
        output_channels: int,
        start_channel: int = 0,
    ):

        self.input_channels = input_channels
        self.output_channels = output_channels
        self.start_channel = start_channel

    def insert(self, data: bytes) -> bytes:
        """
        Bettet einen Datenblock in die volle Kanalzahl ein.
        """

        if (
            self.start_channel == 0
            and self.input_channels >= self.output_channels
        ):
            return data

        input_frame_size = (
            self.input_channels * self.BYTES_PER_SAMPLE
        )

        output_frame_size = (
            self.output_channels * self.BYTES_PER_SAMPLE
        )

        start_offset = (
            self.start_channel * self.BYTES_PER_SAMPLE
        )

        frame_count = len(data) // input_frame_size

        #
        # bytearray ist standardmäßig mit Nullen gefüllt ->
        # nicht belegte Kanäle sind automatisch stumm.
        #
        out = bytearray(frame_count * output_frame_size)

        for frame in range(frame_count):

            src_offset = frame * input_frame_size
            dst_offset = frame * output_frame_size + start_offset

            out[dst_offset:dst_offset + input_frame_size] = (
                data[src_offset:src_offset + input_frame_size]
            )

        return bytes(out)
