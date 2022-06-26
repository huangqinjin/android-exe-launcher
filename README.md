# Android Executable Launcher

## Generate

To generate the launcher package, the following tools are required:

- Host OS: Linux
- Python 3.6+
- `debugfs` included in `e2fsprogs` package.
- Superuser privilege: to mount Android system image.
- Wine (Optional): to generate NuGet package.

Run command:
```shell
./make.py --api 33
```

The launcher package will be placed at `system-images/android-33_r05/arm64-v8a`.

## Consume

To consume the launcher package, the following tools are required:

- `qemu-aarch64` included in `qemu-linux-user` package.

Download the launcher package from [NuGet Gallery](https://www.nuget.org/packages/android-exe-launcher) and unzip or generate by following the [instruction](https://github.com/huangqinjin/android-exe-launcher#generate).

Run command:
```shell
cd /path/to/android_exe
qemu-aarch64 -L /path/to/launcher/package -E LD_LIBRARY_PATH=. ./android_exe
```

Refer to [CMakeTest](https://github.com/huangqinjin/CMakeTest) and [GlogTest](https://github.com/huangqinjin/GlogTest) for examples using the launcher in CMake projects.
