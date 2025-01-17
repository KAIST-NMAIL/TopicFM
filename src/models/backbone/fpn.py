import torch.nn as nn
import torch.nn.functional as F


def conv1x1(in_planes, out_planes, stride=1):
    """1x1 convolution without padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, padding=0, bias=False)


def conv3x3(in_planes, out_planes, stride=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)


class ConvBlock(nn.Module):
    def __init__(self, in_planes, planes, stride=1, bn=True):
        super().__init__()
        self.conv = conv3x3(in_planes, planes, stride)
        self.bn = nn.BatchNorm2d(planes) if bn is True else None
        self.act = nn.GELU()

    def forward(self, x):
        y = self.conv(x)
        if self.bn:
            y = self.bn(y) #F.layer_norm(y, y.shape[1:])
        y = self.act(y)
        return y


class FPN(nn.Module):
    """
    ResNet+FPN, output resolution are 1/8 and 1/2.
    Each block has 2 layers.
    """

    def __init__(self, config):
        super().__init__()
        # Config
        block = ConvBlock
        initial_dim = config['initial_dim']
        block_dims = config['block_dims']

        # Class Variable
        self.in_planes = initial_dim

        # Networks
        self.conv1 = nn.Conv2d(1, initial_dim, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(initial_dim)
        self.relu = nn.ReLU(inplace=True)

        self.layer1 = self._make_layer(block, block_dims[0], stride=1)  # 1/2
        self.layer2 = self._make_layer(block, block_dims[1], stride=2)  # 1/4
        self.layer3 = self._make_layer(block, block_dims[2], stride=2)  # 1/8
        self.layer4 = self._make_layer(block, block_dims[3], stride=2)  # 1/16

        # 3. FPN upsample
        self.layer3_outconv = conv1x1(block_dims[2], block_dims[3])
        self.layer3_outconv2 = nn.Sequential(
            #conv3x3(block_dims[3], block_dims[3]),
            #nn.BatchNorm2d(block_dims[3]),
            #nn.GELU(),
            ConvBlock(block_dims[3], block_dims[2]),
            conv3x3(block_dims[2], block_dims[2]),
        )
        #self.layer3_outconv3 = TrunkBlock(block_dims[2], block_dims[2])
        self.layer2_outconv = conv1x1(block_dims[1], block_dims[2])
        self.layer2_outconv2 = nn.Sequential(
            #conv3x3(block_dims[2], block_dims[2]),
            #nn.BatchNorm2d(block_dims[2]),
            #nn.GELU(),
            ConvBlock(block_dims[2], block_dims[1]),
            conv3x3(block_dims[1], block_dims[1]),
        )
        self.layer1_outconv = conv1x1(block_dims[0], block_dims[1])
        self.layer1_outconv2 = nn.Sequential(
            #conv3x3(block_dims[1], block_dims[1]),
            #nn.BatchNorm2d(block_dims[1]),
            #nn.GELU(),
            #ConvBlock(block_dims[1], block_dims[1]),
            ConvBlock(block_dims[1], block_dims[0]),
            #ConvBlock(block_dims[0], block_dims[0]),
            conv3x3(block_dims[0], block_dims[0]),
        )
        #self.layer1_outconv3 = TrunkBlock(block_dims[0], block_dims[0])

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def _make_layer(self, block, dim, stride=1):
        layer1 = block(self.in_planes, dim, stride=stride)
        layer2 = block(dim, dim, stride=1)
        layers = (layer1, layer2)

        self.in_planes = dim
        return nn.Sequential(*layers)

    def forward(self, x):
        # ResNet Backbone
        x0 = self.relu(self.bn1(self.conv1(x)))
        x1 = self.layer1(x0)  # 1/2
        x2 = self.layer2(x1)  # 1/4
        x3 = self.layer3(x2)  # 1/8
        x4 = self.layer4(x3)  # 1/16

        # FPN
        x4_out_2x = F.interpolate(x4, scale_factor=2., mode='bilinear', align_corners=True)
        x3_out = self.layer3_outconv(x3)
        x3_out = self.layer3_outconv2(x3_out+x4_out_2x)
        #x3_out_norm = self.layer3_outconv3(x3_out)

        x3_out_2x = F.interpolate(x3_out, scale_factor=2., mode='bilinear', align_corners=True)
        x2_out = self.layer2_outconv(x2)
        x2_out = self.layer2_outconv2(x2_out+x3_out_2x)

        x2_out_2x = F.interpolate(x2_out, scale_factor=2., mode='bilinear', align_corners=True)
        x1_out = self.layer1_outconv(x1)
        x1_out = self.layer1_outconv2(x1_out+x2_out_2x)
        #x1_out_norm = self.layer1_outconv3(x1_out)

        return [x3_out, x1_out]
