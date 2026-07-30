from audio.channel_extractor import ChannelExtractor

# Ein Frame mit 18 Kanälen à 4 Byte
data = bytes(range(72))

extractor = ChannelExtractor(
    input_channels=18,
    output_channels=2,
)

result = extractor.extract(data)

print(len(data))
print(len(result))
print(result)
