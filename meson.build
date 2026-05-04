project('ydoit',
  version: '2.0.0',
  license: 'MIT',
  meson_version: '>= 0.62.0',
)

python = import('python')
py_installation = python.find_installation('python3')
python_dir = py_installation.get_install_dir()

# Install Python package (exclude __pycache__)
install_subdir(
  'src/ydoit',
  install_dir: python_dir,
  exclude_directories: ['__pycache__'],
)

# Install launcher scripts to /usr/bin/
install_data(
  'bin/ydoit',
  'bin/ydoit-gui',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

subdir('data')
