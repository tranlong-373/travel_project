import React from 'react'
import NavBar from './NavBar/NavBar'
import Search from './Search'
import kid from '../assets/kid.png'
const Header = () => {
  return (
    <div className='min-h-screen mb-4 bg-cover bg-center flex items-center w-full overflow-hidden'
      style={{ backgroundImage: `url(${kid})` }}
      id='Header'>
        <NavBar/>
        <Search/>
    </div>
  )
}

export default Header