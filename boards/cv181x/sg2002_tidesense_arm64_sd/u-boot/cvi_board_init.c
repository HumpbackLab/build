
static void set_rtc_register_for_power(void)
{
	mmio_write_32(0x050250AC, 0x2);
	mmio_write_32(0x050260D0, 0x3);
	mmio_write_32(0x03001098, 0x0);
	mmio_write_32(0x0300109C, 0x0);
	mmio_write_32(0x03001090, 0x0);
	mmio_write_32(0x03001094, 0x0);
	mmio_write_32(0x05027084, 0x0);
	mmio_write_32(0x05027088, 0x0);
	mmio_write_32(0x0502708C, 0x0);
	mmio_write_32(0x05027090, 0x0);
	mmio_write_32(0x050260BC, 0x1700);
	mmio_write_32(0x05026128, 0x0);
}

int cvi_board_init(void)
{
	/* Set RTC / power defaults before remapping the wakeup pads to GPIOs. */
	set_rtc_register_for_power();

	/* TF socket: SD0, 3.3 V signalling, no connected card-detect switch. */
	PINMUX_CONFIG(SD0_CLK, SDIO0_CLK);
	PINMUX_CONFIG(SD0_CMD, SDIO0_CMD);
	PINMUX_CONFIG(SD0_D0, SDIO0_D_0);
	PINMUX_CONFIG(SD0_D1, SDIO0_D_1);
	PINMUX_CONFIG(SD0_D2, SDIO0_D_2);
	PINMUX_CONFIG(SD0_D3, SDIO0_D_3);
	PINMUX_CONFIG(SD0_CD, SDIO0_CD);
	PINMUX_CONFIG(SD0_PWR_EN, XGPIOA_14);

	/* OV9281 shared I2C2 and camera sync / shutdown GPIOs. */
	PINMUX_CONFIG(PWR_GPIO0, PWR_GPIO_0);
	PINMUX_CONFIG(PWR_GPIO1, IIC2_SCL);
	PINMUX_CONFIG(PWR_GPIO2, IIC2_SDA);
	PINMUX_CONFIG(PWR_WAKEUP0, PWR_GPIO_6);
	PINMUX_CONFIG(PWR_BUTTON1, PWR_GPIO_8);

	/* SC7U22 on SPI2, using the SD1 pad bank; SD1_D2 is unconnected. */
	PINMUX_CONFIG(SD1_D3, SPI2_CS_X);
	PINMUX_CONFIG(SD1_D1, PWR_GPIO_20);
	PINMUX_CONFIG(SD1_D0, SPI2_SDI);
	PINMUX_CONFIG(SD1_CMD, SPI2_SDO);
	PINMUX_CONFIG(SD1_CLK, SPI2_SCK);
	PINMUX_CONFIG(SD1_D2, PWR_GPIO_19);

	/* UART0 remains the console/debug header. */
	PINMUX_CONFIG(UART0_TX, UART0_TX);
	PINMUX_CONFIG(UART0_RX, UART0_RX);

	return 0;
}
