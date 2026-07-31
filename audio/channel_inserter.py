"""
Kanal-Einfügung für die Wiedergabe.
"""


class ChannelInserter:
    """
    Bettet einen interleaved PCM-Datenstrom mit `input_channels`
    Kanälen pro Frame in einen Datenstrom mit `output_channels`
    Kanälen pro Frame ein. Die Eingabe-Kanäle landen auf den ersten
    Kanälen der Ausgabe, alle übrigen Kanäle bleiben stumm (0).

    Gegenstück zu ChannelExtractor: Eine Aufnahme, die z.B. mit 8
    Kanälen aufgenommen wurde, wird so bei der Wiedergabe wieder auf
    genau denselben (ersten 8) Kanälen des Interfaces ausgegeben, da
    das Interface auch bei der Wiedergabe immer mit seiner vollen,
    festen Kanalzahl betrieben werden muss.
    """

    BYTES_PER_SAMPLE = 4

    def __init__(
        self,
        input_channels: int,
        output_channels: int,
    ):

        self.input_channels = input_channels
        self.output_channels = output_channels

    def insert(self, data: bytes) -> bytes:
        """
        Bettet einen Datenblock in die volle Kanalzahl ein.
        """

        if self.input_channels >= self.output_channels:
            return data

        input_frame_size = (
            self.input_channels * self.BYTES_PER_SAMPLE
        )

        output_frame_size = (
            self.output_channels * self.BYTES_PER_SAMPLE
        )

        frame_count = len(data) // input_frame_size

        #
        # bytearray ist standardmäßig mit Nullen gefüllt ->
        # nicht belegte Kanäle sind automatisch stumm.
        #
        out = bytearray(frame_count * output_frame_size)

        for frame in range(frame_count):

            src_offset = frame * input_frame_size
            dst_offset = frame * output_frame_size

            out[dst_offset:dst_offset + input_frame_size] = (
                data[src_offset:src_offset + input_frame_size]
            )

        return bytes(out)
